/**
 * Context Selector - chooses best items to fit budget.
 */

import { ScoredContextItem, ContextBudget } from './types.js';

export class ContextSelector {
  /**
   * Picks the highest scored items within the token budget.
   */
  public select(
    scoredItems: ScoredContextItem[],
    budget: ContextBudget
  ): ScoredContextItem[] {
    const totalBudget = budget.totalTokens;
    let usedTokens = 0;
    
    // Sort by score (descending)
    const sorted = [...scoredItems].sort((a, b) => b.score - a.score);
    const selected: ScoredContextItem[] = [];

    // Critical items go first regardless of budget (safety)
    for (const item of sorted) {
      if (item.priority >= 90) { // CRITICAL
        selected.push(item);
        usedTokens += item.tokens;
      }
    }

    // Now fill remaining budget with high-scoring items
    for (const item of sorted) {
      if (item.priority >= 90) continue; // Already added

      if (usedTokens + item.tokens <= totalBudget) {
        selected.push(item);
        usedTokens += item.tokens;
      } else {
        // Option: we could try to compress the item here,
        // but for now we just skip it to maintain integrity.
      }
    }

    return selected;
  }
}
