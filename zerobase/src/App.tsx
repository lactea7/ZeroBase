/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import Navigation from './components/Navigation';
import Hero from './components/Hero';
import Manual from './components/Manual';

export default function App() {
  return (
    <div className="min-h-screen selection:bg-brand-primary/30 bg-white">
      <Navigation />
      
      <main>
        <Hero />

        <Manual />
      </main>

    </div>
  );
}
