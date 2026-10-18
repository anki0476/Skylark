

import { useCallback, useEffect, useRef, useState } from 'react';

const INTRO_AUTOPLAY_MS = 5000;

const steps = [
 {label:'Choose a fault',title:'Start with the unexpected.',copy:'Choose a reservation scenario and a tool failure: timeout after commit, stale read, or incomplete response.',takeaway:''},
 {label:'Inspect the incident',title:'A timeout is not a rollback.',copy:'Compare the response delivered to the agent with the authoritative sandbox state. Find the duplicate, missed task, or false success.',takeaway:''},
 {label:'Review a repair',title:'Change one thing. Keep the evidence.',copy:'Inspect a proposed prompt change or runtime safeguard before approving a new version.',takeaway:''},
 {label:'Verify recovery',title:'Make the next run count.',copy:'Compare original and repaired outcomes, then export the incident and regression test.',takeaway:'Scripted examples demonstrate the harness. Fresh model evaluations require Nebius.'},
];
function StepExample({active}:{active:number}){
 const examples=[
 [['Tool','create_reservation'],['Fault','Timeout after commit'],['Mode','Scripted fixture']],
 [['Agent observes','Timeout'],['Actual state','Reservation created'],['Unsafe retry','Duplicate reservation']],
 [['Stable operation key','On'],['Reconcile status','On'],['Validate receipt','On']],
 [['Original fixture','Duplicate detected'],['Repaired fixture','One reservation'],['Evidence','Exportable regression test']],
 ];
 return <div className="how-example"><p className="how-example-label">Illustrative sandbox example</p><dl>{examples[active].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>{active===3&&<a className="text-button" href="#/app">Try the demo →</a>}</div>
}

export default function IntroCarousel() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [manualPause,setManualPause]=useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const sectionRef = useRef<HTMLElement>(null);
  const autoplayRemaining = useRef(INTRO_AUTOPLAY_MS);
  const autoplayDeadline = useRef<number | null>(null);
  const effectivePaused = manualPause || paused || !isVisible || !pageVisible;

  const goTo = useCallback((index: number) => {
    const next = (index + steps.length) % steps.length;
    setActive((current) => {
      if (current === next) return current;
      autoplayRemaining.current = INTRO_AUTOPLAY_MS;
      autoplayDeadline.current = null;
      return next;
    });
  }, []);

  useEffect(() => {
    if (effectivePaused || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const delay = Math.max(0, autoplayRemaining.current);
    autoplayDeadline.current = performance.now() + delay;
    const timer = window.setTimeout(() => {
      autoplayDeadline.current = null;
      autoplayRemaining.current = INTRO_AUTOPLAY_MS;
      setActive((current) => (current + 1) % steps.length);
    }, delay);
    return () => {
      window.clearTimeout(timer);
      if (autoplayDeadline.current !== null) {
        autoplayRemaining.current = Math.max(0, autoplayDeadline.current - performance.now());
        autoplayDeadline.current = null;
      }
    };
  }, [active, effectivePaused]);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;
    const observer = new IntersectionObserver(([entry]) => setIsVisible(entry.isIntersecting), { rootMargin: '120px' });
    const onVisibilityChange = () => setPageVisible(document.visibilityState !== 'hidden');
    observer.observe(section);
    onVisibilityChange();
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      observer.disconnect();
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  const step = steps[active];

  return (
    <section className="intro-carousel-section" id="how-it-works" aria-labelledby="intro-carousel-title" ref={sectionRef}>
      <div className="intro-carousel-heading"><h2 id="intro-carousel-title">How it works</h2></div>
      <div
        className="intro-carousel how-explainer"
        role="region"
        aria-roledescription="carousel"
        aria-label="How Skylark works"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocusCapture={() => setPaused(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false);
        }}
      >
        <nav className="how-step-nav" aria-label="How it works steps">
          {steps.map((item, index) => <button type="button" key={item.label} aria-current={active === index ? 'step' : undefined} aria-controls="how-step-panel" onClick={() => goTo(index)}><span>0{index + 1}</span>{item.label}</button>)}
        </nav>
        <div className="how-autoplay-progress" aria-hidden="true">
          <i key={active} className={effectivePaused ? 'is-paused' : ''} />
        </div>
        <div className="intro-slide" id="how-step-panel" aria-live="polite" aria-atomic="true">
          <div className="intro-slide-copy"><h3>{step.title}</h3><p>{step.copy}</p>{active === steps.length - 1 ? <p className="how-takeaway">{step.takeaway}</p> : null}</div>
          <StepExample active={active} />
        </div>
        <div className="how-step-controls"><span>Step {active + 1} of {steps.length}</span><div><button type="button" aria-pressed={manualPause} onClick={()=>setManualPause(!manualPause)}>{manualPause?'Play':'Pause'}</button><button type="button" disabled={active === 0} onClick={() => goTo(active - 1)}>← Previous</button><button type="button" disabled={active === steps.length - 1} onClick={() => goTo(active + 1)}>Next →</button></div></div>
      </div>
    </section>
  );
}
