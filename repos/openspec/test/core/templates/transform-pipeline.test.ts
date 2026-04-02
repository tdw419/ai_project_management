/**
 * SEC-5.3: Transform Applicability and Order Tests
 *
 * Validates that the transform pipeline correctly filters transforms
 * by scope and context, and applies them in deterministic order.
 */

import { describe, expect, it } from 'vitest';
import {
  TransformPipeline,
  openCodeHyphenTransform,
  getTransformPipeline,
  resetTransformPipeline,
} from '../../../src/core/templates/transform-pipeline.js';
import type { Transform, TransformContext } from '../../../src/core/templates/transform-types.js';

describe('SEC-5.3: Transform applicability and order', () => {
  afterEach(() => {
    resetTransformPipeline();
  });

  describe('built-in openCode hyphen transform', () => {
    it('should have correct metadata', () => {
      expect(openCodeHyphenTransform.id).toBe('opencode-hyphen-commands');
      expect(openCodeHyphenTransform.scope).toBe('skill');
      expect(openCodeHyphenTransform.phase).toBe('preWrite');
      expect(typeof openCodeHyphenTransform.priority).toBe('number');
      expect(typeof openCodeHyphenTransform.applies).toBe('function');
      expect(typeof openCodeHyphenTransform.transform).toBe('function');
    });

    it('should apply only for opencode toolId', () => {
      const opencodeCtx: TransformContext = { toolId: 'opencode', workflowId: 'explore' };
      const claudeCtx: TransformContext = { toolId: 'claude', workflowId: 'explore' };

      expect(openCodeHyphenTransform.applies(opencodeCtx)).toBe(true);
      expect(openCodeHyphenTransform.applies(claudeCtx)).toBe(false);
    });

    it('should rewrite /opsx: to /opsx-', () => {
      const input = 'Use /opsx:new to start and /opsx:apply to implement.';
      const result = openCodeHyphenTransform.transform(input, {
        toolId: 'opencode',
        workflowId: 'explore',
      });

      expect(result).toContain('/opsx-new');
      expect(result).toContain('/opsx-apply');
      expect(result).not.toContain('/opsx:');
    });
  });

  describe('pipeline filtering by scope', () => {
    it('skill scope should match skill and both transforms', () => {
      const pipeline = new TransformPipeline();
      // openCodeHyphenTransform is 'skill' scope
      const applicable = pipeline.getApplicable('skill', {
        toolId: 'opencode',
        workflowId: 'explore',
      });
      const ids = applicable.map((t) => t.id);
      expect(ids).toContain('opencode-hyphen-commands');
    });

    it('command scope should not match skill-scoped transforms', () => {
      const pipeline = new TransformPipeline();
      const applicable = pipeline.getApplicable('command', {
        toolId: 'opencode',
        workflowId: 'explore',
      });
      const ids = applicable.map((t) => t.id);
      expect(ids).not.toContain('opencode-hyphen-commands');
    });

    it('skill scope should match both-scoped transforms', () => {
      const pipeline = new TransformPipeline();
      const bothTransform: Transform = {
        id: 'test-both',
        description: 'Test both-scope transform',
        scope: 'both',
        phase: 'preWrite',
        priority: 50,
        applies: () => true,
        transform: (c) => c.toUpperCase(),
      };
      pipeline.register(bothTransform);

      const applicable = pipeline.getApplicable('skill', {
        toolId: 'claude',
        workflowId: 'explore',
      });
      const ids = applicable.map((t) => t.id);
      expect(ids).toContain('test-both');
    });

    it('command scope should match both-scoped transforms', () => {
      const pipeline = new TransformPipeline();
      const bothTransform: Transform = {
        id: 'test-both',
        description: 'Test both-scope transform',
        scope: 'both',
        phase: 'preWrite',
        priority: 50,
        applies: () => true,
        transform: (c) => c.toUpperCase(),
      };
      pipeline.register(bothTransform);

      const applicable = pipeline.getApplicable('command', {
        toolId: 'claude',
        workflowId: 'explore',
      });
      const ids = applicable.map((t) => t.id);
      expect(ids).toContain('test-both');
    });
  });

  describe('pipeline ordering', () => {
    it('should order by phase: preAdapter < postAdapter < preWrite', () => {
      const pipeline = new TransformPipeline();

      const t1: Transform = {
        id: 'prewrite-transform',
        description: 'Late phase',
        scope: 'both',
        phase: 'preWrite',
        priority: 1,
        applies: () => true,
        transform: (c) => c,
      };
      const t2: Transform = {
        id: 'preadapter-transform',
        description: 'Early phase',
        scope: 'both',
        phase: 'preAdapter',
        priority: 1,
        applies: () => true,
        transform: (c) => c,
      };
      const t3: Transform = {
        id: 'postadapter-transform',
        description: 'Mid phase',
        scope: 'both',
        phase: 'postAdapter',
        priority: 1,
        applies: () => true,
        transform: (c) => c,
      };

      pipeline.register(t1);
      pipeline.register(t2);
      pipeline.register(t3);

      const applicable = pipeline.getApplicable('skill', {
        toolId: 'claude',
        workflowId: 'explore',
      });
      const ids = applicable.map((t) => t.id);

      // preAdapter should come before postAdapter, which comes before preWrite
      const idxPre = ids.indexOf('preadapter-transform');
      const idxPost = ids.indexOf('postadapter-transform');
      const idxWrite = ids.indexOf('prewrite-transform');
      expect(idxPre).toBeLessThan(idxPost);
      expect(idxPost).toBeLessThan(idxWrite);
    });

    it('should order by priority within the same phase', () => {
      const pipeline = new TransformPipeline();

      const t1: Transform = {
        id: 'low-priority',
        description: 'Low priority',
        scope: 'both',
        phase: 'preWrite',
        priority: 10,
        applies: () => true,
        transform: (c) => c,
      };
      const t2: Transform = {
        id: 'high-priority',
        description: 'High priority',
        scope: 'both',
        phase: 'preWrite',
        priority: 1,
        applies: () => true,
        transform: (c) => c,
      };

      pipeline.register(t1);
      pipeline.register(t2);

      const applicable = pipeline.getApplicable('skill', {
        toolId: 'claude',
        workflowId: 'explore',
      });
      const ids = applicable.map((t) => t.id);

      const idxLow = ids.indexOf('low-priority');
      const idxHigh = ids.indexOf('high-priority');
      expect(idxHigh).toBeLessThan(idxLow);
    });
  });

  describe('pipeline run', () => {
    it('should apply matching transforms and return result with applied IDs', () => {
      const pipeline = new TransformPipeline();
      const result = pipeline.run('skill', 'Use /opsx:new to begin.', {
        toolId: 'opencode',
        workflowId: 'new',
      });

      expect(result.content).toContain('/opsx-new');
      expect(result.appliedTransforms).toContain('opencode-hyphen-commands');
    });

    it('should not apply transforms for non-matching context', () => {
      const pipeline = new TransformPipeline();
      const result = pipeline.run('skill', 'Use /opsx:new to begin.', {
        toolId: 'claude',
        workflowId: 'new',
      });

      expect(result.content).toBe('Use /opsx:new to begin.');
      expect(result.appliedTransforms).toHaveLength(0);
    });

    it('runForSkill convenience method should use skill scope', () => {
      const pipeline = new TransformPipeline();
      const result = pipeline.runForSkill('Use /opsx:new.', {
        toolId: 'opencode',
        workflowId: 'new',
      });
      expect(result.appliedTransforms).toContain('opencode-hyphen-commands');
    });

    it('runForCommand convenience method should use command scope', () => {
      const pipeline = new TransformPipeline();
      const result = pipeline.runForCommand('Use /opsx:new.', {
        toolId: 'opencode',
        workflowId: 'new',
      });
      // openCode hyphen transform is skill-scoped, so it should NOT apply for command
      expect(result.appliedTransforms).toHaveLength(0);
    });

    it('should chain multiple transforms in order', () => {
      const pipeline = new TransformPipeline();
      const append: Transform = {
        id: 'append-marker',
        description: 'Appends a marker',
        scope: 'both',
        phase: 'preWrite',
        priority: 200, // runs after hyphen transform
        applies: () => true,
        transform: (c) => c + ' [APPENDED]',
      };
      pipeline.register(append);

      const result = pipeline.run('skill', 'Use /opsx:new.', {
        toolId: 'opencode',
        workflowId: 'new',
      });

      expect(result.content).toContain('/opsx-new');
      expect(result.content).toContain('[APPENDED]');
      expect(result.appliedTransforms).toEqual([
        'opencode-hyphen-commands',
        'append-marker',
      ]);
    });
  });

  describe('singleton pipeline', () => {
    it('getTransformPipeline should return the same instance', () => {
      const a = getTransformPipeline();
      const b = getTransformPipeline();
      expect(a).toBe(b);
    });

    it('resetTransformPipeline should create a new instance', () => {
      const a = getTransformPipeline();
      resetTransformPipeline();
      const b = getTransformPipeline();
      expect(a).not.toBe(b);
    });

    it('singleton should include built-in transforms', () => {
      const pipeline = getTransformPipeline();
      const all = pipeline.getAll();
      const ids = all.map((t) => t.id);
      expect(ids).toContain('opencode-hyphen-commands');
    });
  });
});
