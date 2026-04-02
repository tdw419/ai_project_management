import { describe, it, expect } from 'vitest';
import type { CommandContent, ToolCommandAdapter, GeneratedCommand, InstallContext } from '../../../src/core/command-generation/types.js';

describe('command-generation/types', () => {
  describe('InstallContext interface', () => {
    it('should allow creating project-scoped context', () => {
      const context: InstallContext = { scope: 'project' };
      expect(context.scope).toBe('project');
    });

    it('should allow creating global-scoped context', () => {
      const context: InstallContext = { scope: 'global' };
      expect(context.scope).toBe('global');
    });
  });

  describe('CommandContent interface', () => {
    it('should allow creating valid command content', () => {
      const content: CommandContent = {
        id: 'explore',
        name: 'OpenSpec Explore',
        description: 'Enter explore mode for thinking',
        category: 'Workflow',
        tags: ['workflow', 'explore'],
        body: 'This is the command body content.',
      };

      expect(content.id).toBe('explore');
      expect(content.name).toBe('OpenSpec Explore');
      expect(content.description).toBe('Enter explore mode for thinking');
      expect(content.category).toBe('Workflow');
      expect(content.tags).toEqual(['workflow', 'explore']);
      expect(content.body).toBe('This is the command body content.');
    });

    it('should allow empty tags array', () => {
      const content: CommandContent = {
        id: 'test',
        name: 'Test',
        description: 'Test command',
        category: 'Test',
        tags: [],
        body: 'Body',
      };

      expect(content.tags).toEqual([]);
    });
  });

  describe('ToolCommandAdapter interface contract', () => {
    it('should implement adapter with getFilePath and formatFile', () => {
      const mockAdapter: ToolCommandAdapter = {
        toolId: 'test-tool',
        getFilePath(commandId: string): string {
          return `.test/${commandId}.md`;
        },
        formatFile(content: CommandContent): string {
          return `---\nname: ${content.name}\n---\n\n${content.body}\n`;
        },
      };

      expect(mockAdapter.toolId).toBe('test-tool');
      expect(mockAdapter.getFilePath('explore')).toBe('.test/explore.md');

      const content: CommandContent = {
        id: 'test',
        name: 'Test Command',
        description: 'Desc',
        category: 'Cat',
        tags: [],
        body: 'Body content',
      };

      const formatted = mockAdapter.formatFile(content);
      expect(formatted).toContain('name: Test Command');
      expect(formatted).toContain('Body content');
    });

    it('should accept InstallContext in getFilePath', () => {
      const scopedAdapter: ToolCommandAdapter = {
        toolId: 'scoped-test',
        getFilePath(commandId: string, context?: InstallContext): string {
          if (context?.scope === 'global') {
            return `/home/user/.test/${commandId}.md`;
          }
          return `.test/${commandId}.md`;
        },
        formatFile(content: CommandContent): string {
          return content.body;
        },
      };

      // Without context (backward compat)
      expect(scopedAdapter.getFilePath('explore')).toBe('.test/explore.md');

      // With project context
      expect(scopedAdapter.getFilePath('explore', { scope: 'project' })).toBe('.test/explore.md');

      // With global context
      expect(scopedAdapter.getFilePath('explore', { scope: 'global' })).toBe('/home/user/.test/explore.md');
    });
  });

  describe('GeneratedCommand interface', () => {
    it('should represent generated command output', () => {
      const generated: GeneratedCommand = {
        path: '.claude/commands/opsx/explore.md',
        fileContent: '---\nname: Test\n---\n\nBody\n',
      };

      expect(generated.path).toBe('.claude/commands/opsx/explore.md');
      expect(generated.fileContent).toContain('name: Test');
    });
  });
});
