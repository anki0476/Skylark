"""Fixed scenario packs. No generation or tuning based on observed outcomes."""
import math
import uuid
from .domain import Scenario, Fault, RunSpec, Policy, freeze, digest
from .provider import Settings
from .runner import work_once


def pack(split="held_out"):
    kinds = ["timeout_after_commit", "stale_read", "incomplete_response"]
    return [Scenario(name=f"{split} / {kind} / case {index+1}", resource=f"room-{index+1}",
        customer=f"Synthetic user {index+1}", intent_id=f"{split}-{kind}-{index+1}", capacity=[2,3,1,2][index],
        seed=(100 if split=="held_out" else 10)+index, split=split, fault=Fault(kind=kind))
        for kind in kinds for index in range(4 if split=="held_out" else 1)]


def schedule(db, mode="fixture", trials=3, split="held_out"):
    scenarios=pack(split)
    model=Settings.load().snapshot() if mode=="live" else None
    specs=[]
    for scenario in scenarios:
        for trial in range(trials):
            for repaired in (False,True):
                specs.append(RunSpec(mode=mode,scenario=scenario,policy=Policy(stable_key=repaired,reconcile=repaired,validate_receipt=repaired)))
    # Three control tasks, each under the original and repaired configuration.
    for index in range(3):
        for repaired in (False,True):
            specs.append(RunSpec(mode=mode,scenario=Scenario(name=f"Control {index+1}",intent_id=f"control-{index+1}",split="control",fault=Fault(kind="none")),
                                 policy=Policy(stable_key=repaired,reconcile=repaired,validate_receipt=repaired)))
    if mode=="live":
        settings=Settings.load()
        upper=len(specs)*8*2*(24000*settings.input_rate+settings.max_tokens*settings.output_rate)
        if db.budget()["accounted_usd"]*1e6+upper>settings.cap_usd*1e6:
            raise ValueError("Full protocol exceeds the configured maximum allowance. Predeclare fewer trials before collecting results.")
    ident=uuid.uuid4().hex
    snapshots=[(uuid.uuid4().hex,freeze(spec,model)) for spec in specs]
    payload={"kind":"benchmark","mode":mode,"trials":trials,"split":split,"pack_hash":digest([s.model_dump() for s in scenarios]),
             "runs":[key for key,_ in snapshots],"notice":"Synthetic scenarios; fixture results are not model evidence."}
    db.schedule_comparison(ident,payload,snapshots)
    return {"id":ident,**payload}
