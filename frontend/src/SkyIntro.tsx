import {useEffect, useRef, useState} from 'react';
import {ArrowRight, X} from 'lucide-react';
import skyFlight from './assets/sky-flight.png';
import skyWave from './assets/sky-wave.png';

const seenKey = 'skylark.sky.intro.seen.v1';

function firstVisit() {
  try { return localStorage.getItem(seenKey) !== '1'; }
  catch { return true; }
}

export function SkyIntro() {
  const [visible, setVisible] = useState(firstVisit);
  const [ready, setReady] = useState(false);
  const [arrived, setArrived] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const flightRef = useRef<HTMLDivElement>(null);
  const skipRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!visible) return;
    try { localStorage.setItem(seenKey, '1'); } catch { /* The intro still works without storage. */ }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    skipRef.current?.focus();

    let frame = 0;
    let greetingTimer = 0;
    let settled = false;
    let cancelled = false;
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const bird = flightRef.current;
    const position = (x: number, y: number, angle = 0, scale = 1) => {
      if (!bird) return;
      bird.style.setProperty('--sky-x', `${x}px`);
      bird.style.setProperty('--sky-y', `${y}px`);
      bird.style.setProperty('--sky-angle', `${angle}deg`);
      bird.style.setProperty('--sky-scale', String(scale));
    };
    const spriteSize = () => innerWidth < 700
      ? Math.min(innerWidth * .65, 280, innerHeight * .38)
      : Math.min(innerWidth * .34, 390, innerHeight * .52);
    const destination = () => {
      const width = innerWidth;
      const height = innerHeight;
      const size = spriteSize();
      return {
        x: width < 700 ? (width - size) / 2 : width * .71 - size / 2,
        y: width < 700 ? Math.max(32, height * .16) : Math.max(24, height * .39 - size / 2),
      };
    };

    const onResize = () => {
      if (reducedMotion || settled) {
        const goal = destination();
        position(goal.x, goal.y);
      }
    };
    window.addEventListener('resize', onResize);

    const launch = () => {
    if (cancelled) return;
    setReady(true);
    if (reducedMotion) {
      const goal = destination();
      position(goal.x, goal.y);
      settled = true;
      setArrived(true);
      setSpeaking(true);
    } else {
      const size = spriteSize();
      let x = -size * 1.2;
      let y = innerHeight * .72;
      let vx = innerWidth * .62;
      let vy = -innerHeight * .7;
      let last = performance.now();
      const started = last;
      position(x, y, -15, .72);

      const fly = (now: number) => {
        const dt = Math.min((now - last) / 1000, .032);
        const elapsed = (now - started) / 1000;
        last = now;
        const goal = destination();
        // A damped spring steers SKY toward a landing point. The raised guide
        // point creates an arc; velocity determines pitch and the spring settles
        // naturally instead of stopping at a keyframe.
        const arcProgress = Math.min(elapsed / 2.2, 1);
        const guideY = goal.y - Math.sin(arcProgress * Math.PI) * innerHeight * .13;
        vx += ((goal.x - x) * 15 - vx * 6.2) * dt;
        vy += ((guideY - y) * 15 - vy * 6.2) * dt;
        x += vx * dt;
        y += vy * dt;
        const pitch = Math.max(-18, Math.min(15, vy / innerHeight * 26));
        const scale = .72 + .28 * Math.min(elapsed / 1.8, 1);
        position(x, y, pitch, scale);
        if (elapsed < 2.7) {
          frame = requestAnimationFrame(fly);
        } else {
          position(goal.x, goal.y);
          settled = true;
          setArrived(true);
          greetingTimer = window.setTimeout(() => setSpeaking(true), 280);
        }
      };
      frame = requestAnimationFrame(fly);
    }
    };
    if (reducedMotion) launch();
    else {
      const poses = Array.from(bird?.querySelectorAll('img') ?? []);
      void Promise.all(poses.map(image => image.decode().catch(() => {}))).then(launch);
    }

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      clearTimeout(greetingTimer);
      window.removeEventListener('resize', onResize);
      document.body.style.overflow = previousOverflow;
    };
  }, [visible]);

  if (!visible) return null;
  const dismiss = () => setVisible(false);
  return <div className={`sky-intro${arrived ? ' sky-intro-arrived' : ''}`} role="dialog" aria-modal="true" aria-label="Meet SKY" onKeyDown={event => {
    if (event.key === 'Escape') dismiss();
    if (event.key !== 'Tab') return;
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button'));
    if (buttons.length === 1) { event.preventDefault(); buttons[0].focus(); return; }
    if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1)?.focus(); }
    if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus(); }
  }}>
    <div className="sky-intro-wash" aria-hidden="true"/>
    <button ref={skipRef} className="sky-intro-skip" onClick={dismiss}>Skip intro <X size={16}/></button>
    {!ready && <span className="sky-intro-loading" role="status">SKY is on the way…</span>}
    <div ref={flightRef} className="sky-flight" aria-hidden="true">
      <div className="sky-bird">
        <img className="sky-pose sky-pose-flight" src={skyFlight} alt="" decoding="async"/>
        <img className="sky-pose sky-pose-wave" src={skyWave} alt="" decoding="async"/>
      </div>
    </div>
    {speaking && <div className="sky-intro-card" aria-live="polite">
      <span className="sky-intro-kicker">MEET YOUR GUIDE</span>
      <h2>Hi, I’m SKY!</h2>
      <p>Welcome to Skylark. Here you can test how an AI agent handles tool failures, see what really happened, and compare a repair.</p>
      <button className="primary pop-button" onClick={dismiss}>Let’s explore <ArrowRight size={17}/></button>
    </div>}
  </div>;
}
