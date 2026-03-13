import os
import re

for filename in os.listdir('routes'):
    if not filename.endswith('.py') or filename == 'auth.py':
        continue
    
    filepath = os.path.join('routes', filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    new_lines = []
    
    skip_next_login = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # Check if line has @app.route or bp.route
        match = re.search(r'@\w+_bp\.route', line)
        if match:
            # check the next line if it already has @login_required
            has_login = False
            if i + 1 < len(lines) and '@login_required' in lines[i+1]:
                has_login = True
                
            # Exclude landing, privacy, terms
            func_line = lines[i+1] if i+1 < len(lines) else ""
            if i+2 < len(lines) and not func_line.strip().startswith('def '):
                # might be multi line route decorator or maybe next line is login required
                func_line = lines[i+2]
            
            # Look for def signature closely
            is_public = False
            for j in range(1, 4):
                if i+j < len(lines):
                    l_strip = lines[i+j].strip()
                    if l_strip.startswith('def '):
                        if l_strip.startswith('def landing(') or l_strip.startswith('def privacy_policy(') or l_strip.startswith('def terms_of_service('):
                            is_public = True
                        break
            
            if not has_login and not is_public:
                new_lines.append("    @login_required\n" if line.startswith("    ") else "@login_required\n")

    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
print("Fixed routes")
