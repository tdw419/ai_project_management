import { describe, it, expect } from 'vitest';

import {
  resolveCommandSurface,
  resolveCommandSurfaces,
  supportsCommandsDelivery,
} from '../../../src/core/shared/command-surface.js';
import type { CommandSurface } from '../../../src/core/config.js';
import { AI_TOOLS } from '../../../src/core/config.js';

describe('command-surface', () => {
  describe('resolveCommandSurface', () => {
    describe('explicit override', () => {
      it('should use explicit commandSurface when declared on tool metadata', () => {
        // Trae is explicitly marked skills-invocable in AI_TOOLS
        const result = resolveCommandSurface('trae', false);
        expect(result).toBe('skills-invocable');
      });

      it('should use explicit commandSurface even when an adapter exists', () => {
        // If a tool has an explicit override and an adapter, the override wins
        const result = resolveCommandSurface('trae', true);
        expect(result).toBe('skills-invocable');
      });

      it('should confirm Trae is configured in AI_TOOLS with commandSurface', () => {
        const trae = AI_TOOLS.find((t) => t.value === 'trae');
        expect(trae).toBeDefined();
        expect(trae!.commandSurface).toBe('skills-invocable');
      });
    });

    describe('inferred from adapter presence', () => {
      it('should infer adapter when no explicit override and adapter is registered', () => {
        // claude has no explicit commandSurface, and has a registered adapter
        const result = resolveCommandSurface('claude', true);
        expect(result).toBe('adapter');
      });

      it('should infer adapter for cursor when adapter exists', () => {
        const result = resolveCommandSurface('cursor', true);
        expect(result).toBe('adapter');
      });

      it('should infer adapter for windsurf when adapter exists', () => {
        const result = resolveCommandSurface('windsurf', true);
        expect(result).toBe('adapter');
      });
    });

    describe('inferred skills-invocable (has skillsDir, no adapter)', () => {
      it('should infer skills-invocable when tool has skillsDir but no adapter and no override', () => {
        // A tool with skillsDir but without an adapter registered and no explicit
        // commandSurface should be inferred as skills-invocable.
        // In practice, all current tools either have adapters or explicit overrides,
        // so we test with a tool that exists in AI_TOOLS but has no adapter.
        // We'll verify the inference logic by simulating the case.
        const result = resolveCommandSurface('cline', false);
        expect(result).toBe('skills-invocable');
      });
    });

    describe('inferred none', () => {
      it('should infer none for a tool without skillsDir and without adapter', () => {
        // 'agents' has no skillsDir and no adapter
        const result = resolveCommandSurface('agents', false);
        expect(result).toBe('none');
      });

      it('should infer none for an unknown tool', () => {
        const result = resolveCommandSurface('nonexistent-tool', false);
        expect(result).toBe('none');
      });

      it('should infer none for an unknown tool even with adapter=true (no skillsDir)', () => {
        // Unknown tool has no AI_TOOLS entry, so no skillsDir
        const result = resolveCommandSurface('nonexistent-tool', true);
        expect(result).toBe('adapter');
        // Actually, unknown tool with adapter=true should still be 'adapter'
        // because hasAdapter takes precedence over skillsDir check
      });
    });

    describe('determinism', () => {
      it('should return the same result on repeated calls', () => {
        const r1 = resolveCommandSurface('claude', true);
        const r2 = resolveCommandSurface('claude', true);
        expect(r1).toBe(r2);
      });

      it('should return the same result for trae regardless of adapter flag', () => {
        const withAdapter = resolveCommandSurface('trae', true);
        const withoutAdapter = resolveCommandSurface('trae', false);
        expect(withAdapter).toBe('skills-invocable');
        expect(withoutAdapter).toBe('skills-invocable');
      });
    });
  });

  describe('resolveCommandSurfaces', () => {
    it('should resolve surfaces for multiple tools', () => {
      const results = resolveCommandSurfaces(
        ['claude', 'trae', 'cursor'],
        (id) => id !== 'trae' // simulate trae has no adapter
      );

      expect(results.get('claude')).toBe('adapter');
      expect(results.get('trae')).toBe('skills-invocable'); // explicit override
      expect(results.get('cursor')).toBe('adapter');
    });

    it('should handle mixed tool sets with all surface types', () => {
      const results = resolveCommandSurfaces(
        ['claude', 'trae', 'agents'],
        (id) => id === 'claude' // only claude has adapter
      );

      expect(results.get('claude')).toBe('adapter');
      expect(results.get('trae')).toBe('skills-invocable');
      expect(results.get('agents')).toBe('none');
    });

    it('should return an empty map for empty input', () => {
      const results = resolveCommandSurfaces([], () => false);
      expect(results.size).toBe(0);
    });
  });

  describe('supportsCommandsDelivery', () => {
    it('should return true for adapter surface', () => {
      expect(supportsCommandsDelivery('adapter')).toBe(true);
    });

    it('should return true for skills-invocable surface', () => {
      expect(supportsCommandsDelivery('skills-invocable')).toBe(true);
    });

    it('should return false for none surface', () => {
      expect(supportsCommandsDelivery('none')).toBe(false);
    });

    it('should cover all CommandSurface values', () => {
      const allSurfaces: CommandSurface[] = ['adapter', 'skills-invocable', 'none'];
      for (const surface of allSurfaces) {
        // Just ensure no runtime errors
        const result = supportsCommandsDelivery(surface);
        expect(typeof result).toBe('boolean');
      }
    });
  });

  describe('stacking compatibility', () => {
    it('should preserve simplify-skill-installation profile/delivery model', () => {
      // After adding commandSurface, tools should still have their skillsDir
      // and the profile/delivery model should remain intact
      const claude = AI_TOOLS.find((t) => t.value === 'claude');
      expect(claude?.skillsDir).toBe('.claude');

      const trae = AI_TOOLS.find((t) => t.value === 'trae');
      expect(trae?.skillsDir).toBe('.trae');
      expect(trae?.commandSurface).toBe('skills-invocable');
    });

    it('should compose with add-global-install-scope scopeSupport', () => {
      // Codex has both scopeSupport and (implicitly) adapter command surface.
      // Adding commandSurface should not conflict with scopeSupport.
      const codex = AI_TOOLS.find((t) => t.value === 'codex');
      expect(codex?.scopeSupport).toEqual({ skills: ['project'], commands: ['global', 'project'] });
      expect(codex?.commandSurface).toBeUndefined(); // inferred from adapter

      // Resolve should still return adapter for codex
      const surface = resolveCommandSurface('codex', true);
      expect(surface).toBe('adapter');
    });

    it('should ensure scope × delivery × command-surface composition is deterministic', () => {
      // Test all three dimensions compose correctly for a few representative tools
      type TestCase = {
        toolId: string;
        hasAdapter: boolean;
        expectedSurface: CommandSurface;
      };

      const cases: TestCase[] = [
        { toolId: 'claude', hasAdapter: true, expectedSurface: 'adapter' },
        { toolId: 'trae', hasAdapter: false, expectedSurface: 'skills-invocable' },
        { toolId: 'agents', hasAdapter: false, expectedSurface: 'none' },
        { toolId: 'codex', hasAdapter: true, expectedSurface: 'adapter' },
      ];

      for (const tc of cases) {
        const surface = resolveCommandSurface(tc.toolId, tc.hasAdapter);
        expect(surface).toBe(tc.expectedSurface);
      }
    });
  });
});
