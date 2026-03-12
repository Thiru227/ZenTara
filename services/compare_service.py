import logging
from config import Config

logger = logging.getLogger(__name__)


def _get_ai_compare_fn():
    """Get the comparison functions from the configured AI provider."""
    if Config.AI_PROVIDER == 'claude':
        from services.claude_service import compare_two_carriers_ai
        return compare_two_carriers_ai
    else:
        from services.gemini_service import compare_carriers_with_ai
        return compare_carriers_with_ai


def _get_ai_version_compare_fn():
    """Get the version comparison function from the configured AI provider."""
    if Config.AI_PROVIDER == 'claude':
        from services.claude_service import compare_two_carriers_ai
        # Claude's compare function takes two carrier data dicts
        return lambda v1, v2, name: compare_two_carriers_ai(v1, v2)
    else:
        from services.gemini_service import compare_versions_with_ai
        return compare_versions_with_ai


def compare_two_carriers(carrier1, carrier2):
    """Compare two carriers side by side."""
    def get_clause_value(clauses, clause_type):
        for c in clauses:
            if isinstance(c, dict) and c.get('clause_type') == clause_type:
                return c.get('extracted_value', 'N/A')
            elif hasattr(c, 'clause_type') and c.clause_type == clause_type:
                return c.extracted_value or 'N/A'
        return 'N/A'

    def get_carrier_clauses(carrier):
        from models.sla import SLADocument, ExtractedClause
        active_sla = SLADocument.query.filter_by(carrier_id=carrier.id, is_active=True).first()
        if not active_sla:
            return []
        return ExtractedClause.query.filter_by(sla_document_id=active_sla.id).all()

    clauses1 = get_carrier_clauses(carrier1)
    clauses2 = get_carrier_clauses(carrier2)

    comparison_fields = [
        ('claim_deadline', 'Claim Filing Window', 'days'),
        ('liability', 'Liability Cap', 'amount'),
        ('penalty', 'Penalty Clause', 'text'),
        ('pickup_commitment', 'Pickup SLA', 'percent'),
        ('payment_terms', 'Payment Terms', 'days'),
    ]

    rows = []
    for field_type, field_label, unit in comparison_fields:
        val1 = get_clause_value(clauses1, field_type)
        val2 = get_clause_value(clauses2, field_type)
        rows.append({
            'label': field_label,
            'carrier1_value': val1,
            'carrier2_value': val2,
            'advantage': _determine_advantage(field_type, val1, val2)
        })

    # Get AI summary
    carrier1_data = {
        'name': carrier1.name,
        'clauses': [c.to_dict() if hasattr(c, 'to_dict') else c for c in clauses1]
    }
    carrier2_data = {
        'name': carrier2.name,
        'clauses': [c.to_dict() if hasattr(c, 'to_dict') else c for c in clauses2]
    }
    
    ai_result = _get_ai_compare_fn()(carrier1_data, carrier2_data)
    # ai_result may be a dict with 'summary' and 'recommendation' keys
    if isinstance(ai_result, dict):
        ai_summary_text = ai_result.get('summary', '')
        ai_recommendation = ai_result.get('recommendation', '')
        if ai_recommendation:
            ai_summary_text += ' ' + ai_recommendation
    else:
        ai_summary_text = str(ai_result) if ai_result else ''

    return {
        'carrier1': {'name': carrier1.name, 'id': carrier1.id},
        'carrier2': {'name': carrier2.name, 'id': carrier2.id},
        'rows': rows,
        'ai_summary': ai_summary_text
    }


def compare_two_versions(sla_v1, sla_v2, carrier_name):
    """Compare two versions of the same carrier's SLA."""
    from models.sla import ExtractedClause
    
    clauses_v1 = ExtractedClause.query.filter_by(sla_document_id=sla_v1.id).all()
    clauses_v2 = ExtractedClause.query.filter_by(sla_document_id=sla_v2.id).all()

    def clauses_to_dict(clauses):
        return {c.clause_type: c for c in clauses}

    map_v1 = clauses_to_dict(clauses_v1)
    map_v2 = clauses_to_dict(clauses_v2)
    all_types = set(list(map_v1.keys()) + list(map_v2.keys()))

    changes = []
    for clause_type in all_types:
        c1 = map_v1.get(clause_type)
        c2 = map_v2.get(clause_type)

        if c1 and not c2:
            changes.append({'type': 'removed', 'clause': c1.to_dict(), 'impact': 'neutral'})
        elif c2 and not c1:
            changes.append({'type': 'added', 'clause': c2.to_dict(), 'impact': 'neutral'})
        elif c1 and c2:
            if c1.extracted_value != c2.extracted_value or c1.clause_text != c2.clause_text:
                impact = _assess_change_impact(clause_type, c1.extracted_value, c2.extracted_value)
                changes.append({
                    'type': 'modified',
                    'old': c1.to_dict(),
                    'new': c2.to_dict(),
                    'impact': impact
                })

    # AI changelog summary
    v1_data = {'version_label': sla_v1.version_label, 'clauses': [c.to_dict() for c in clauses_v1]}
    v2_data = {'version_label': sla_v2.version_label, 'clauses': [c.to_dict() for c in clauses_v2]}
    
    ai_summary = _get_ai_version_compare_fn()(v1_data, v2_data, carrier_name)

    has_negative = any(c.get('impact') == 'negative' for c in changes)
    tara_reaction = 'stressed' if has_negative else 'calm'

    return {
        'v1': sla_v1.to_dict(),
        'v2': sla_v2.to_dict(),
        'changes': changes,
        'ai_summary': ai_summary,
        'tara_reaction': tara_reaction
    }


def _determine_advantage(field_type, val1, val2):
    """Determine which carrier has the advantage for a given field."""
    import re
    
    if val1 == 'N/A' or val2 == 'N/A':
        return 'unknown'
    
    # Extract numeric values
    nums1 = re.findall(r'\d+\.?\d*', str(val1))
    nums2 = re.findall(r'\d+\.?\d*', str(val2))
    
    if not nums1 or not nums2:
        return 'equal'
    
    n1, n2 = float(nums1[0]), float(nums2[0])
    
    # Higher is better for: liability cap, pickup commitment, dispute win rate
    # Lower is better for: claim deadline window (fewer days = stricter)
    if field_type in ['claim_deadline', 'payment_terms']:
        if n1 > n2: return 'carrier1'
        elif n2 > n1: return 'carrier2'
    elif field_type in ['liability', 'pickup_commitment']:
        if n1 > n2: return 'carrier1'
        elif n2 > n1: return 'carrier2'
    
    return 'equal'


def _assess_change_impact(clause_type, old_value, new_value):
    """Assess if a change is positive, negative, or neutral for the user."""
    import re
    
    if not old_value or not new_value:
        return 'neutral'
    
    old_nums = re.findall(r'\d+\.?\d*', str(old_value))
    new_nums = re.findall(r'\d+\.?\d*', str(new_value))
    
    if not old_nums or not new_nums:
        return 'neutral'
    
    old_n, new_n = float(old_nums[0]), float(new_nums[0])
    
    # Reduced claim window = NEGATIVE for user
    if clause_type == 'claim_deadline' and new_n < old_n:
        return 'negative'
    # Increased liability = POSITIVE
    elif clause_type == 'liability' and new_n > old_n:
        return 'positive'
    elif clause_type == 'liability' and new_n < old_n:
        return 'negative'
    
    return 'neutral'
