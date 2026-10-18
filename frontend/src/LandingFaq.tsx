

import { useState } from 'react';

const questions = [
 {id:'purpose',question:'What does Skylark test?',answer:'How tool-using agents recover from timeouts, stale reads, and incomplete responses. It checks safety, task completion, reporting accuracy, and whether the fault actually triggered.'},
 {id:'start',question:'Do I need an API key to try it?',answer:'No. The scripted fixture runs locally without inference charges. Fresh model evaluations require a configured Nebius account and confirmed credits.'},
 {id:'live',question:'Is the demo a real model evaluation?',answer:'The supplied fixture is scripted and tests the harness. Live evaluations make new model calls and are labeled separately. Fixture results are not evidence of model reliability.'},
 {id:'privacy',question:'Where does my agent run?',answer:'Trusted agent adapters run locally. Live inference sends task and tool messages to Nebius. Only calls routed through the adapter are instrumented.'},
 {id:'repairs',question:'Does Skylark change my code automatically?',answer:'No. You review a supported configuration or prompt repair before approval. The original evidence is preserved, and generated source code is not executed.'},
 {id:'exports',question:'Can I export the results?',answer:'Yes. Download an incident bundle with evidence and a regression test, or export the results as JSON.'},
];

export default function LandingFaq() {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <section className="faq-section" aria-labelledby="faq-title">
      <div className="faq-heading">
        <h2 id="faq-title">Frequently Asked Questions</h2>
      </div>

      <div className="faq-list">
        {questions.map((item, index) => {
          const isExpanded = expanded === item.id;
          const panelId = `faq-panel-${item.id}`;

          return (
            <article className={`faq-item ${isExpanded ? 'is-expanded' : ''}`} key={item.id}>
              <button
                type="button"
                aria-expanded={isExpanded}
                aria-controls={panelId}
                onClick={() => setExpanded((current) => current === item.id ? null : item.id)}
              >
                <span className="faq-number">0{index + 1}</span>
                <span className="faq-question">{item.question}</span>
                <span className="faq-chevron" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m6 9 6 6 6-6" /></svg></span>
              </button>
              <div className="faq-answer" id={panelId} hidden={!isExpanded}>
                <div><p>{item.answer}</p></div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
