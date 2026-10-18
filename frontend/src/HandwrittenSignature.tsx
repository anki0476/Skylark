



const englishSignatureWords = ['Built', 'with', '❤️', 'for', 'Agents'];
const hindiSignatureWords = ['भारतीयों', 'के', 'लिए', '❤️', 'से', 'बनाया'];

export default function HandwrittenSignature() {
  const language: string = 'en';
  const signatureWords = language === 'hi' ? hindiSignatureWords : englishSignatureWords;
  return (
    <div className="handwritten-signature" aria-label={language === 'hi' ? 'भारतीयों के लिए प्रेम से निर्मित · अंकित श्रीवास्तव' : 'Built with love for Agents by Ankit Shrivastava'}>
      <span className="signature-split-flap" aria-hidden="true">
        {signatureWords.map((word) => (
          <span className="signature-split-flap-word" key={word}>
            {(word === '❤️' ? [word] : Array.from(word)).map((character, index) => (
              <span
                className={`signature-split-flap-tile${word === '❤️' ? ' is-heart' : ''}`}
                key={`${character}-${index}`}
              >
                <span className="signature-split-flap-half signature-split-flap-top">
                  <span>{character}</span>
                </span>
                <span className="signature-split-flap-half signature-split-flap-bottom">
                  <span>{character}</span>
                </span>
              </span>
            ))}
          </span>
        ))}
      </span>
      <span className="signature-credit" aria-hidden="true">{language === 'hi' ? 'अंकित श्रीवास्तव द्वारा' : 'by Ankit Shrivastava'}</span>
    </div>
  );
}
