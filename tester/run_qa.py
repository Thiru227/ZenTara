"""
ZenTara Q&A Test Runner (Optimized)
====================================
Sends all 30 questions in a SINGLE Claude call with the full SLA context,
then parses the batch response. Much faster and cheaper than 30 individual calls.

Usage:  python tester/run_qa.py
"""
import sys, os, json, re, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(override=True)

# ── Q&A pairs (question, key expected values, clause ref) ────────
QA_PAIRS = [
    ("What is the deadline to file a visible damage claim?",
     ["21", "calendar days", "delivery date"], "4.1"),
    ("What is the deadline to file a loss claim?",
     ["60", "calendar days", "shipment date"], "4.1"),
    ("How long to request a service failure credit for a late Priority Overnight?",
     ["15", "calendar days"], "4.1"),
    ("What is the billing dispute deadline?",
     ["30", "calendar days", "invoice"], "4.1"),
    ("What is the overcharge claim deadline?",
     ["45", "calendar days"], "4.1"),
    ("What type of claim for broken contents but no visible damage, and its deadline?",
     ["concealed", "21", "calendar days"], "4.1"),
    ("How quickly will FedEx acknowledge a submitted claim?",
     ["2", "business days"], "4.4"),
    ("Resolution timeline for a standard damage claim?",
     ["5", "7", "business days"], "4.4"),
    ("What happens if billing dispute submitted on day 32?",
     ["rejected"], "4.1"),
    ("Deadline to file international loss claim under Warsaw Convention?",
     ["120", "calendar days"], "4.1"),
    ("Standard declared value for FedEx Express domestic?",
     ["100", "usd"], "5.1"),
    ("Max liability for a laptop via FedEx Ground with no excess coverage?",
     ["1,000", "1000", "electronics"], "5.1"),
    ("Maximum declared value via excess coverage?",
     ["50,000", "50000"], "5.2"),
    ("Max liability for FedEx Freight LTL shipment?",
     ["25", "per pound", "50,000"], "5.1"),
    ("Can Horizon sue FedEx for lost sales revenue from a late shipment?",
     ["no", "waiv", "consequential"], "5.3"),
    ("Liability for shipping an antique table worth $8,000?",
     ["1,000", "1000"], "5.1"),
    ("On-time percentage for Priority Overnight?",
     ["99", "99.0"], "3.1"),
    ("Credit when FedEx misses a Ground delivery commitment?",
     ["100%", "credit", "shipping charge"], "3.3"),
    ("Monthly cap on total service credits?",
     ["20%", "monthly"], "7.1"),
    ("When do unused credits expire?",
     ["12", "months"], "7.1"),
    ("What can customer do if Express on-time below threshold for 3 consecutive months?",
     ["terminat", "30"], "7.1"),
    ("International Economy on-time delivery commitment?",
     ["95", "95.0"], "3.1"),
    ("Credit for a missed scheduled pickup?",
     ["25", "usd"], "6.3"),
    ("Deadline to request pickup failure credit?",
     ["10", "business days"], "4.1"),
    ("Scheduled pickup window for Horizon Logistics?",
     ["4:00", "6:00", "monday", "saturday"], "6.2"),
    ("Notice required to terminate without cause?",
     ["60", "days", "written"], "9.1"),
    ("Early termination fee if cancelled in month 8?",
     ["48,000", "48000", "10%"], "9.4"),
    ("Advance notice for rate changes?",
     ["30", "days", "written"], "8.2"),
    ("Customer objection window for SLA term changes?",
     ["15", "days"], "8.2"),
    ("Negotiated discount rates for Horizon?",
     ["18%", "12%", "15%", "10%"], "11.2"),
]


def run_batch_test():
    """Send all 30 questions in ONE Claude API call."""
    print("=" * 70)
    print("  ZenTara Q&A Validation — Batch Mode")
    print("  FedEx SLA v1.0 | 30 Questions | Single API Call")
    print("=" * 70)
    print()

    # Load SLA
    sla_path = os.path.join('tester', 'FedEx_SLA_v1.0_ZenTara.txt')
    with open(sla_path, 'r', encoding='utf-8') as f:
        sla_text = f.read()
    print(f"  SLA loaded: {len(sla_text)} chars")

    # Build numbered question list
    questions_block = "\n".join(
        f"Q{i+1}: {q}" for i, (q, _, _) in enumerate(QA_PAIRS)
    )

    prompt = f"""You are a contract analysis expert. Read the following SLA document carefully, then answer ALL 30 questions below.

For EACH question, respond with EXACTLY this format:
A1: [your answer]
A2: [your answer]
...through A30.

Keep each answer to 1-2 concise sentences. Always cite the section number.

=== SLA DOCUMENT ===
{sla_text}

=== QUESTIONS ===
{questions_block}

Answer all 30 questions now. Start with A1:"""

    print(f"  Prompt size: {len(prompt)} chars")
    print(f"  Sending to Claude... ", end="", flush=True)

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get('CLAUDE_API_KEY', ''))

    start_time = time.time()
    message = client.messages.create(
        model='claude-haiku-4-5',
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    elapsed = time.time() - start_time

    response_text = message.content[0].text
    print(f"done! ({elapsed:.1f}s, {message.usage.input_tokens} in / {message.usage.output_tokens} out)")
    print()

    # Parse answers
    answers = {}
    for match in re.finditer(r'A(\d+):\s*(.+?)(?=\nA\d+:|\Z)', response_text, re.DOTALL):
        num = int(match.group(1))
        text = match.group(2).strip()
        answers[num] = text

    # Score each answer
    passed = 0
    partial = 0
    failed = 0
    results = []

    for i, (question, keywords, clause) in enumerate(QA_PAIRS):
        q_num = i + 1
        answer = answers.get(q_num, "[NO ANSWER]")
        answer_lower = answer.lower()

        # Count keyword matches
        found = 0
        total_kw = len(keywords)
        matched = []
        missed = []

        for kw in keywords:
            if kw.lower() in answer_lower:
                found += 1
                matched.append(kw)
            else:
                missed.append(kw)

        score = found / max(total_kw, 1)

        if score >= 0.6:
            status = "PASS"
            passed += 1
            icon = "✅"
        elif score >= 0.3:
            status = "PARTIAL"
            partial += 1
            icon = "🟡"
        else:
            status = "FAIL"
            failed += 1
            icon = "❌"

        results.append({
            'q': q_num, 'status': status, 'score': round(score, 2),
            'clause': clause, 'matched': matched, 'missed': missed,
            'answer': answer[:150]
        })

        print(f"  {icon} Q{q_num:02d} [{status:7s}] §{clause:5s}  {question[:55]}")
        if status != "PASS":
            print(f"     Answer: {answer[:90]}")
            if missed:
                print(f"     Missing: {', '.join(missed)}")

    total = len(QA_PAIRS)
    avg_score = sum(r['score'] for r in results) / max(total, 1)

    print()
    print("=" * 70)
    print("  RESULTS SUMMARY")
    print("=" * 70)
    print(f"  Total:    {total}")
    print(f"  ✅ Pass:  {passed} ({passed/total*100:.0f}%)")
    print(f"  🟡 Part:  {partial} ({partial/total*100:.0f}%)")
    print(f"  ❌ Fail:  {failed} ({failed/total*100:.0f}%)")
    print(f"  Avg Score: {avg_score:.0%}")
    print(f"  API Time:  {elapsed:.1f}s | Tokens: {message.usage.input_tokens}+{message.usage.output_tokens}")
    print()

    if avg_score >= 0.85:
        grade = "🎉 EXCELLENT"
    elif avg_score >= 0.7:
        grade = "👍 GOOD"
    elif avg_score >= 0.5:
        grade = "⚠️  NEEDS WORK"
    else:
        grade = "🔴 POOR"
    print(f"  GRADE: {grade}")
    print("=" * 70)

    # Save results
    results_path = os.path.join('tester', 'qa_results.json')
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'model': 'claude-haiku-4-5',
            'api_time_seconds': round(elapsed, 1),
            'input_tokens': message.usage.input_tokens,
            'output_tokens': message.usage.output_tokens,
            'total': total, 'passed': passed, 'partial': partial, 'failed': failed,
            'avg_score': round(avg_score, 3),
            'results': results
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {results_path}")


if __name__ == '__main__':
    run_batch_test()
