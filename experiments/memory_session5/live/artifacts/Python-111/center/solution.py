def histogram(test):
    dict1={}
    list1=test.split(" ")
    if not list1 or list1 == ['']:
        return dict1
    max_count = max(list1.count(i) for i in list1 if i != '')
    for i in list1:
        if i != '' and list1.count(i) == max_count:
            dict1[i] = max_count
    return dict1
