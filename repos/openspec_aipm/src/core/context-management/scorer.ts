/**
 * Context Scorer - weights content by task relevance.
 */

import { ContextItem, ScoredContextItem, PRIORITY } from './types.js';

export class ContextScorer {
  /**
   * Scores items based on relevance to the current task.
   */
  public score(
    items: ContextItem[],
    taskDescription: string,
    attemptNumber: number
  ): ScoredContextItem[] {
    return items.map(item => {
      let score = item.priority;

      // Boost items based on tags and attempt
      if (attemptNumber > 1 && item.tags.includes('failure')) {
        score += 20;
      }

      if (attemptNumber > 1 && item.tags.includes('strategy')) {
        score += 15;
      }

      // Keyword matching (simple relevance)
      const keywords = taskDescription.toLowerCase().split(/\s+/);
      const content = item.content.toLowerCase();
      
      let keywordMatches = 0;
      for (const word of keywords) {
        if (word.length > 3 && content.includes(word)) {
          keywordMatches++;
        }
      }

      // Adjust score by matches, capped at a reasonable boost
      score += Math.min(keywordMatches * 5, 25);

      return {
        ...item,
        score,
        tokens: this.estimateTokens(item.content)
      };
    });
  }

  /**
   * Very rough token estimation (approx 4 chars per token).
   */
  private estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }
}
