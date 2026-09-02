// Renders the component with react-dom/server. Requires `npm install react
// react-dom` first; the package itself ships no dependencies, so this file is
// skipped when they are not present.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';

let renderToStaticMarkup;
try {
  ({ renderToStaticMarkup } = await import('react-dom/server'));
} catch {
  test('react binding', { skip: 'react-dom not installed' }, () => {});
}

const { SemanticText } = await import('../src/SemanticText.js');
const render = (props) => renderToStaticMarkup(createElement(SemanticText, props));

if (renderToStaticMarkup) {
  test('renders the passage verbatim', () => {
    const text = 'The deploy failed, but the rollback was clean.';
    const html = render({ text });
    assert.equal(html.replace(/<[^>]+>/g, ''), text);
  });

  test('styles only the words that earned it', () => {
    const html = render({ text: 'the file is in the folder with the other one', as: 'p' });
    assert.ok(!html.includes('<span'), html);
  });

  test('children work as well as the text prop', () => {
    assert.equal(render({ children: 'a disaster' }), render({ text: 'a disaster' }));
  });

  test('an element per styled word, plain runs coalesced', () => {
    const html = render({ text: 'this was an absolute disaster of a release', theme: 'loud' });
    assert.ok(html.includes('color-mix'));
    assert.ok((html.match(/<span/g) || []).length < 5);
  });

  test('renders as any element and forwards props', () => {
    const html = render({ text: 'hello', as: 'p', className: 'lede', id: 'x' });
    assert.ok(html.startsWith('<p'));
    assert.ok(html.includes('class="lede"') && html.includes('id="x"'));
  });

  test('a disabled channel emits none of its styling', () => {
    const html = render({ text: 'an absolute disaster', theme: 'loud', channels: ['salience'] });
    assert.ok(!html.includes('color-mix(in oklab, currentColor'));
  });

  test('debug exposes the scores as data attributes', () => {
    const html = render({ text: 'a catastrophic regression', theme: 'loud', debug: true });
    assert.ok(html.includes('data-valence='));
  });

  test('empty and undefined text do not throw', () => {
    assert.equal(render({ text: '' }), '<span></span>');
    assert.equal(render({}), '<span></span>');
  });
}

if (renderToStaticMarkup) {
  test('a single channel emits exactly one property', () => {
    const text = 'The migration ran clean. In production it deleted the index.';
    const colour = render({ text, channels: ['valence'] });
    assert.ok(colour.includes('color-mix'));
    assert.ok(!colour.includes('font-weight') && !colour.includes('font-size'));

    const weight = render({ text, channels: ['salience'] });
    assert.ok(weight.includes('font-weight'));
    assert.ok(!weight.includes('color-mix'));
  });

  test('a theme can switch an axis off without touching the channel', () => {
    const text = 'WARNING: this deletes production data.';
    assert.ok(render({ text }).includes('font-size'));
    assert.ok(!render({ text, theme: { size: { range: 0 } } }).includes('font-size'));
  });
}
