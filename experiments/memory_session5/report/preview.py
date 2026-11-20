from layout import *
from known import *
from retrieval import *
from intro import *
p('Какие данные сохранить после прерывания работы агента','Title')
methods();packets();transfer_packets();serbench();masking();policy();diagnosis();literature();endpage()
folder=HERE/'preview';folder.mkdir(exist_ok=True)
doc.save(folder/'agent-memory-session5-results.docx')
