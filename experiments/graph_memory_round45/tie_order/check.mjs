/** Exhaustive author self-check. Run: node check.mjs [--write] */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const directory = path.dirname(fileURLToPath(import.meta.url));
const file = name => path.join(directory, name);
const digest = name => createHash('sha256').update(readFileSync(file(name))).digest('hex');

function sumsByMask(values) {
  const sums = new Array(1 << values.length).fill(0);
  for (let mask = 1; mask < sums.length; mask++) {
    const lowest = mask & -mask;
    sums[mask] = sums[mask ^ lowest] + values[Math.log2(lowest)];
  }
  return sums;
}

function prefix(costs, present, threshold) {
  let head = 0;
  let cost = 0;
  for (let i = 0; i < costs.length; i++) {
    if (!(present & (1 << i))) continue;
    if (cost + costs[i] > threshold) break;
    cost += costs[i];
    head |= 1 << i;
  }
  return head;
}

function exactOptima(present, head, budget, costsByMask, gainsByMask) {
  let best = -Infinity;
  let tied = [];
  for (let s = present; ; s = (s - 1) & present) {
    if ((s & head) === head && costsByMask[s] <= budget) {
      if (gainsByMask[s] > best) {
        best = gainsByMask[s];
        tied = [];
      }
      if (gainsByMask[s] === best) tied.push(s);
    }
    if (s === 0) break;
  }
  return tied;
}

function strictDP(costs, gains, present, head, capacity) {
  const values = new Array(capacity + 1).fill(0);
  const masks = new Array(capacity + 1).fill(0);
  for (let i = 0; i < costs.length; i++) {
    const bit = 1 << i;
    if (!(present & bit) || (head & bit)) continue;
    for (let cap = capacity; cap >= costs[i]; cap--) {
      const prev = cap - costs[i];
      const value = values[prev] + gains[i];
      if (value > values[cap]) {
        values[cap] = value;
        masks[cap] = masks[prev] | bit;
      }
    }
  }
  return head | masks[capacity];
}

function choose(candidates, key) {
  return candidates.reduce((left, right) => key(right) > key(left) ? right : left);
}

function solve(costs, gains, present, budget, threshold, costsByMask, gainsByMask, counts) {
  const head = prefix(costs, present, threshold);
  const tied = exactOptima(present, head, budget, costsByMask, gainsByMask);
  const choices = [
    choose(tied, s => -s),
    choose(tied, s => s),
    choose(tied, s => (149 * s + 37) % 257),
  ];
  assert.equal(strictDP(costs, gains, present, head, budget - costsByMask[head]), choices[0]);
  counts.strict_dp_checks++;
  return { head, choices, ties: tied.length };
}

function enumerate() {
  const c = { source_tasks: 0, comparisons: 0, zero_cost_comparisons: 0,
    zero_budget_comparisons: 0, multiple_optima_after_deletion: 0,
    strict_dp_checks: 0, violations: 0 };
  for (let n = 0; n <= 4; n++) {
    const all = (1 << n) - 1;
    for (let index = 0; index < 9 ** n; index++) {
      let code = index;
      const costs = [], gains = [];
      for (let i = 0; i < n; i++) {
        const digit = code % 9;
        code = Math.floor(code / 9);
        costs.push(digit % 3);
        gains.push(Math.floor(digit / 3) - 1);
      }
      const prices = sumsByMask(costs), utilities = sumsByMask(gains);
      for (let budget = 0; budget <= 3; budget++) {
        for (let threshold = 0; threshold <= budget; threshold++) {
          c.source_tasks++;
          const base = solve(costs, gains, all, budget, threshold, prices, utilities, c);
          for (let present = 0; present <= all; present++) {
            const next = solve(costs, gains, present, budget, threshold, prices, utilities, c);
            if (next.ties > 1) c.multiple_optima_after_deletion++;
            for (let k = 0; k < base.choices.length; k++) {
              const packet = base.choices[k];
              const reusable = (present & packet) === packet && (next.head & packet) === next.head;
              if (reusable !== (next.choices[k] === packet)) c.violations++;
              c.comparisons++;
              if (costs.includes(0)) c.zero_cost_comparisons++;
              if (budget === 0) c.zero_budget_comparisons++;
            }
          }
        }
      }
    }
  }
  assert.equal(c.violations, 0);
  return c;
}

function ids(mask, n) {
  return Array.from({length: n}, (_, i) => i).filter(i => mask & (1 << i));
}

function counterexample() {
  const costs = [2, 1, 1, 1], gains = [1, 2, 1, 1];
  const budget = 2, threshold = 1;
  const prices = sumsByMask(costs), utilities = sumsByMask(gains);
  function run(present) {
    const head = prefix(costs, present, threshold);
    const tied = exactOptima(present, head, budget, prices, utilities);
    const key = s => {
      const tail = s & ~head;
      return ids(tail, 4).length % 2 ? tail : -tail;
    };
    return { head: ids(head, 4), equally_optimal: tied.map(p => ids(p, 4)),
      tail_tie_choice: ids(choose(tied, key), 4),
      strict_dp_choice: ids(strictDP(costs, gains, present, head, budget - prices[head]), 4) };
  }
  const before = run(15), after = run(14);
  assert.deepEqual(before.tail_tie_choice, [1, 2]);
  assert.deepEqual(after.tail_tie_choice, [1, 3]);
  assert.deepEqual(before.strict_dp_choice, after.strict_dp_choice);
  const criterion = !before.tail_tie_choice.includes(0) && after.head.every(i => before.tail_tie_choice.includes(i));
  assert.equal(criterion, true);
  return { costs, gains, budget, threshold, deleted: [0], criterion, before, after };
}

const result = { enumeration: enumerate(), counterexample: counterexample() };
const json = JSON.stringify(result, null, 2) + '\n';
if (process.argv.includes('--write')) {
  writeFileSync(file('results.json'), json);
} else {
  assert.deepEqual(result, JSON.parse(readFileSync(file('results.json'))));
  const manifest = JSON.parse(readFileSync(file('manifest.json')));
  for (const [name, hash] of Object.entries(manifest.files)) assert.equal(digest(name), hash);
}
console.log(json);
