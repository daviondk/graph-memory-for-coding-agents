def histogram(test):
    dict1={}
    list1=test.split(" ")
    if not list1 or list1 == ['']:
        return dict1
    t=0
    for i in list1:
        if i != '':
            if(list1.count(i)>t):
                t=list1.count(i)
    if t>0:
        for i in list1:
            if i != '' and list1.count(i)==t:
                dict1[i]=t
    return dict1
