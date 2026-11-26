"""Boundary fixtures, including rare end censoring absent from the main clean cohort."""
from count import windows,h,D,save

def run():
    root=[(1,"edit","f")];n=dict(last=10,run_error=False)
    def simulate(s,expected,starts=None,loose=False,report=n):
        x=windows(root+s,0,"f",report,starts or {},loose)
        assert (x["stop"],x["reads"])==expected
        return [x["stop"],x["reads"]]
    out={}
    out["unknown_log_end"]=simulate([],("trace_end_unverified",0))
    out["failed_run_end"]=simulate([],("trace_end_error",0),report=dict(last=10,run_error=True))
    out["explicit_finish"]=simulate([(8,"finish")],("finished",0))
    out["same_file_ack"]=simulate([(3,"write_start","f"),(5,"edit","f")],("mutation",0),{3:(5,"str_replace",h("f"))})
    out["unrelated_file"]=simulate([(2,"read","other",[[1,"h"]],1),(8,"finish")],("finished",0))
    out["unconfirmed"]=simulate([(3,"write_start","f")],("unconfirmed_write",0))
    out["uncertain_overlap"]=simulate([(4,"write_start","f"),(5,"read","f",[[8,"h"]],1),(6,"edit","f")],("inflight_write",0),{4:(6,"str_replace",h("f"))})
    out["discard_uncertain"]=simulate([(2,"barrier"),(3,"read","f",[[1,"h"]],1),(8,"finish")],("opaque",0))
    out["count_logged_past_uncertainty"]=simulate([(2,"barrier"),(3,"read","f",[[1,"h"]],1),(8,"finish")],("finished",1),loose=True)
    out["gap_irrespective_of_terminal_policy"]=simulate([(2.5,"gap"),(3,"read","f",[[1,"h"]],1),(8,"finish")],("gap",0),loose=True)
    out["strict_empty_read"]=simulate([(3,"read","f",[],1),(8,"finish")],("finished",0))
    save(D/"fixtures.json",out)
if __name__=="__main__":run()
