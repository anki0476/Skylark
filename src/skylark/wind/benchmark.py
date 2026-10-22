"""Fixed scenario packs. No generation or tuning based on observed outcomes."""
import math
import uuid
from .domain import Scenario, Fault, RunSpec, Policy, STALE_READ_FOLLOWUP, freeze, digest
from .provider import Settings
from .runner import work_once


def pack(split="held_out", mode="fixture", cases_per_fault=None):
    if split not in ("development", "held_out"):
        raise ValueError("Unknown benchmark split")
    available = 4 if split == "held_out" else 1
    count = available if cases_per_fault is None else cases_per_fault
    if type(count) is not int or not 1 <= count <= available:
        raise ValueError(f"Choose 1 to {available} predeclared cases per fault for this split")
    kinds = ["timeout_after_commit", "stale_read", "incomplete_response"]
    return [Scenario(name=f"{split} / {kind} / case {index+1}", resource=f"room-{index+1}",
        customer=f"Synthetic user {index+1}", intent_id=f"{split}-{kind}-{index+1}", capacity=[2,3,1,2][index],
        seed=(100 if split=="held_out" else 10)+index, split=split, fault=Fault(kind=kind),
        task_message=STALE_READ_FOLLOWUP if mode=="live" and kind=="stale_read" else "")
        for kind in kinds for index in range(count)]


def schedule(db, mode="fixture", trials=3, split="held_out", cases_per_fault=None, freshness_guard=False):
    scenarios=pack(split, mode, cases_per_fault)
    if type(freshness_guard) is not bool:
        raise ValueError("Freshness guard must be enabled or disabled")
    selected_cases=len(scenarios)//3
    model=Settings.load().snapshot() if mode=="live" else None
    specs=[]
    for scenario in scenarios:
        for trial in range(trials):
            for repaired in (False,True):
                specs.append(RunSpec(mode=mode,scenario=scenario,policy=Policy(stable_key=repaired,reconcile=repaired,validate_receipt=repaired,
                    validate_freshness=repaired and freshness_guard)))
    # Three control tasks, each under the original and repaired configuration.
    for index in range(3):
        for repaired in (False,True):
            specs.append(RunSpec(mode=mode,scenario=Scenario(name=f"Control {index+1}",intent_id=f"control-{index+1}",split="control",fault=Fault(kind="none")),
                                 policy=Policy(stable_key=repaired,reconcile=repaired,validate_receipt=repaired,
                                     validate_freshness=repaired and freshness_guard)))
    if mode=="live":
        settings=Settings.load()
        upper=len(specs)*8*2*math.ceil(24000*settings.input_rate+settings.max_tokens*settings.output_rate)
        if db.budget(include_attempts=False)["accounted_micros"]+upper>int(settings.cap_usd*1_000_000):
            raise ValueError("Protocol exceeds the configured maximum allowance. Predeclare fewer cases or trials before collecting results.")
    ident=uuid.uuid4().hex
    snapshots=[(uuid.uuid4().hex,freeze(spec,model)) for spec in specs]
    payload={"kind":"benchmark","mode":mode,"trials":trials,"split":split,"cases_per_fault":selected_cases,
             "freshness_guard":freshness_guard,"pack_hash":digest([s.model_dump() for s in scenarios]),
             "protocol_hash":digest([snapshot for _,snapshot in snapshots]),
             "runs":[key for key,_ in snapshots],"notice":"Synthetic scenarios; fixture results are not model evidence."}
    db.schedule_comparison(ident,payload,snapshots)
    return {"id":ident,**payload}
