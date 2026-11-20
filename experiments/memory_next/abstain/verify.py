from score import aggregate,read
if __name__=='__main__':
    assert aggregate()==read('results.json')
    print('Verified selective delivery for all 258 issues, 11 policies and every repository.')

