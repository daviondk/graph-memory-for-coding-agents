"""Sign operator versions before calculating any test metric."""
from inputs import *
def capture():
    receipt=HERE/'analysis-lock.json'
    if receipt.exists():
        rec=load(receipt)
        for n,d in rec['files'].items():assert sha(HERE/n)==d
        return
    assert not (HERE/'test-seal.json').exists() and not (HERE/'test-results.json').exists()
    names=['PROTOCOL_RU.md','plan.json','dev-results.json','test-inputs.json','inputs.py','predict.py','score.py','verify.py','fetch_model.py','run.ps1']
    save(receipt,{'files':{n:sha(HERE/n) for n in names},'existing_test_forecasts':len(list((HERE/'forecasts/test').glob('*.json.gz'))),'all_test_forecasts_sealed':False,'test_outcomes_opened':False,'scope':'preregistered test selection and unchanged operators, after development smoke'})
if __name__=='__main__':capture()
