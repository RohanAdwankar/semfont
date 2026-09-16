import { useState } from 'react';
import { useChat } from '@ai-sdk/react';
import { SemanticText } from 'semfont';

const text = (m) => m.parts.filter((p) => p.type === 'text').map((p) => p.text).join('');

export function App() {
  const [input, setInput] = useState('');
  const { messages, sendMessage, status } = useChat();
  const busy = status === 'submitted' || status === 'streaming';

  return (
    <main>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!input.trim() || busy) return;
          sendMessage({ text: input });
          setInput('');
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask something"
          aria-label="message"
          autoFocus
        />
      </form>

      {messages.map((m) =>
        m.role === 'user' ? (
          <p key={m.id} className="you"><b>you</b> {text(m)}</p>
        ) : (
          // The same reply twice, so the difference is the only thing on screen.
          // A real app renders the right-hand column alone.
          <div key={m.id} className="reply">
            <section>
              <h2>plain text</h2>
              <p>{text(m)}</p>
            </section>
            <section>
              <h2>semfont</h2>
              <SemanticText as="p" text={text(m)} />
            </section>
          </div>
        ),
      )}
    </main>
  );
}
