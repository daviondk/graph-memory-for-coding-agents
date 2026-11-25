"""Bytewise fold replay from an allowlisted packet containing no same-fold labels."""
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from unittest.mock import patch

import crossfit
from freeze import D, dump, digest, read


def main():
    count=0
    for fold in range(5):
        required=['features.json.gz','feature-lock.json','training-lock.json',f'train-excluding-{fold}.json.gz']
        with TemporaryDirectory() as temp:
            root=Path(temp)
            for name in required:shutil.copyfile(D/name,root/name)
            opened=[]
            def guarded(path):
                assert path.parent==root and path.name in required
                opened.append(path.name)
                return read(path)
            with patch.object(crossfit,'D',root),patch.object(crossfit,'read',guarded):
                crossfit.one_fold(fold)
            assert set(opened)==set(required)
            for n in [f'forecast-{fold}.json.gz',f'model-{fold}.json']:
                assert (root/n).read_bytes()==(D/n).read_bytes()
            count+=len(read(D/f'forecast-{fold}.json.gz'))
    dump(D/'verify-receipt.json',dict(rows=count,identity='byte-for-byte forecasts and fitted model in all 5 folds',
         scope='Only observable features, hash locks and exclusively other-fold outcome labels allowed in fold training.',
         checker=digest(Path(__file__)),results=digest(D/'results.json')))
    print('Verified',count,'cross-fitted forecasts')


if __name__=='__main__':main()

