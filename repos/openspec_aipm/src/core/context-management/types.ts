/**
 * Types for the context management system.
 */

export interface ContextItem {
  id: string;
  content: string;
  priority: number; // Higher is more important
  tags: string[];
  metadata?: Record<string, any>;
}

export interface ContextBudget {
  totalTokens: number;
  sections: Record<string, number>; // Section name -> percentage (0-1)
}

export interface ScoredContextItem extends ContextItem {
  score: number;
  tokens: number;
}

export const PRIORITY = {
  CRITICAL: 100, // Tasks, Instructions
  HIGH: 75,     // Failure history, Strategy
  MEDIUM: 50,   // Proposal, Change-level learnings
  LOW: 25,      // Global learnings, Design docs
  OPTIONAL: 10  // Background, redundant info
};
