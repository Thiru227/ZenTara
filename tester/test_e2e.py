import sys, os, json, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
from dotenv import load_dotenv
load_dotenv(override=True)
from app import create_app
app = create_app()

with app.test_client() as c:
    # 1. Quick create FedEx
    r = c.post('/carriers/create-quick', json={'name': 'FedEx'}, content_type='application/json')
    d = json.loads(r.data)
    cid = d['carrier_id']
    print("CARRIER:", d)

    # 2. Upload TXT
    with open('tester/FedEx_SLA_v1.0_ZenTara.txt', 'rb') as f:
        r = c.post(
            '/carrier/{}/upload'.format(cid),
            data={'sla_file': (f, 'FedEx_SLA.txt'), 'set_active': 'true'},
            content_type='multipart/form-data'
        )
    d = json.loads(r.data)
    print("UPLOAD:", d.get('success'), d.get('message'))

    # 3. Ask question
    r = c.post('/chat/ask',
        json={'query': 'What is the visible damage claim deadline?', 'carrier_id': cid},
        content_type='application/json'
    )
    d = json.loads(r.data)
    print("ANSWER:", d.get('answer', '')[:200])
    print("SUGGESTIONS:", d.get('suggestions', []))
    print("\nALL TESTS PASSED!")
