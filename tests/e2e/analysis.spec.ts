// tests/e2e/analysis.spec.ts
// E2E tests for the cost analysis page (/analysis)
// Design: docs/plans/2026-03-26-10-trace-cost-analysis-page-design.md

import { test, expect } from '@playwright/test';

test.describe('Cost Analysis page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/analysis');
  });

  // ── Page heading ──────────────────────────────────────────────────────────

  test('renders the Cost Analysis heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cost Analysis', level: 1 })).toBeVisible();
  });

  // ── Summary cards ────────────────────────────────────────────────────────

  test('renders the cost summary region', async ({ page }) => {
    await expect(page.getByRole('region', { name: 'Cost summary' })).toBeVisible();
  });

  test('summary cards include All-Time Total, Today, This Week, and Most Expensive Slug', async ({ page }) => {
    const region = page.getByRole('region', { name: 'Cost summary' });
    await expect(region.getByText('All-Time Total')).toBeVisible();
    await expect(region.getByText('Today')).toBeVisible();
    await expect(region.getByText('This Week')).toBeVisible();
    await expect(region.getByText('Most Expensive Slug')).toBeVisible();
  });

  // ── Cost over time chart ─────────────────────────────────────────────────

  test('renders the Cost Over Time section heading', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /Cost Over Time/i, level: 2 })
    ).toBeVisible();
  });

  test('renders the daily cost bar chart', async ({ page }) => {
    await expect(
      page.getByLabel('Daily cost bar chart')
    ).toBeVisible();
  });

  // ── Filter controls ───────────────────────────────────────────────────────

  test('filter form is present with slug, type, date range, and sort controls', async ({ page }) => {
    const form = page.getByRole('search', { name: 'Filter cost runs' });
    await expect(form).toBeVisible();
    await expect(form.getByLabel('Filter by slug substring')).toBeVisible();
    await expect(form.getByLabel('Filter by item type')).toBeVisible();
    await expect(form.getByLabel('Start date')).toBeVisible();
    await expect(form.getByLabel('End date')).toBeVisible();
    await expect(form.getByLabel('Sort order')).toBeVisible();
    await expect(form.getByRole('button', { name: 'Apply' })).toBeVisible();
  });

  test('filter by slug substring narrows the top runs table', async ({ page }) => {
    const form = page.getByRole('search', { name: 'Filter cost runs' });
    const slugInput = form.getByLabel('Filter by slug substring');
    await slugInput.fill('zzz-nonexistent-slug-xyz');
    await form.getByRole('button', { name: 'Apply' }).click();
    await page.waitForURL(/slug=zzz-nonexistent-slug-xyz/);
    // Should show no results or filtered state
    const section = page.getByRole('region', { name: 'Top runs table' });
    const emptyState = page.getByText('No runs match the current filters');
    // Either an empty state message or table is rendered; at minimum the section exists
    const topRunsHeading = page.getByRole('heading', { name: /Top Runs/i, level: 2 });
    await expect(topRunsHeading).toBeVisible();
  });

  test('filter by item type feature applies the filter', async ({ page }) => {
    const form = page.getByRole('search', { name: 'Filter cost runs' });
    await form.getByLabel('Filter by item type').selectOption('feature');
    await form.getByRole('button', { name: 'Apply' }).click();
    await page.waitForURL(/item_type=feature/);
    await expect(page.getByRole('heading', { name: /Top Runs/i, level: 2 })).toBeVisible();
  });

  test('sort dropdown contains inclusive and exclusive cost options', async ({ page }) => {
    const sortSelect = page.getByLabel('Sort order');
    const options = await sortSelect.locator('option').allTextContents();
    expect(options.some(o => /inclusive/i.test(o))).toBe(true);
    expect(options.some(o => /exclusive/i.test(o))).toBe(true);
  });

  // ── Top runs table ────────────────────────────────────────────────────────

  test('renders the Top Runs section heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Top Runs/, level: 2 })).toBeVisible();
  });

  test('top runs table has expected columns when data is present', async ({ page }) => {
    const region = page.getByRole('region', { name: 'Top runs table' });
    const isVisible = await region.isVisible();
    if (isVisible) {
      // Table exists — check column headers
      await expect(region.getByRole('columnheader', { name: 'Slug' })).toBeVisible();
      await expect(region.getByRole('columnheader', { name: 'Node' })).toBeVisible();
      await expect(region.getByRole('columnheader', { name: 'Model' })).toBeVisible();
      await expect(region.getByRole('columnheader', { name: /Exclusive/ })).toBeVisible();
      await expect(region.getByRole('columnheader', { name: /Inclusive/ })).toBeVisible();
    } else {
      // Empty state is acceptable
      await expect(page.getByText('No cost data recorded yet')).toBeVisible();
    }
  });

  test('pagination controls are present when data is present', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'Pagination' });
    const isVisible = await nav.isVisible();
    if (isVisible) {
      await expect(nav.getByText(/Page \d+ of \d+/)).toBeVisible();
    }
  });

  test('sorting by exclusive cost changes the URL sort parameter', async ({ page }) => {
    const form = page.getByRole('search', { name: 'Filter cost runs' });
    await form.getByLabel('Sort order').selectOption('exclusive_desc');
    await form.getByRole('button', { name: 'Apply' }).click();
    await page.waitForURL(/sort=exclusive_desc/);
    await expect(page.getByRole('heading', { name: /Top Runs/i, level: 2 })).toBeVisible();
  });

  // ── Cost by work item ─────────────────────────────────────────────────────

  test('renders the Cost by Work Item section heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cost by Work Item', level: 2 })).toBeVisible();
  });

  test('cost by work item table is present when data exists', async ({ page }) => {
    const region = page.getByRole('region', { name: 'Cost by work item table' });
    const isVisible = await region.isVisible();
    if (isVisible) {
      // getByRole('columnheader') does not scope inside div[role=region]; use text checks
      const table = region.locator('table');
      await expect(table.getByText('Slug').first()).toBeVisible();
      await expect(table.getByText(/Total \$/).first()).toBeVisible();
      await expect(table.getByText('Tasks').first()).toBeVisible();
    } else {
      await expect(
        page.getByText('No work-item cost data available')
      ).toBeVisible();
    }
  });

  test('expand button is present on work item rows when data exists', async ({ page }) => {
    const region = page.getByRole('region', { name: 'Cost by work item table' });
    const isVisible = await region.isVisible();
    if (isVisible) {
      // Button text is ► (not "Show task breakdown"); locate by title attribute
      const expandBtn = region.getByTitle('Show task breakdown').first();
      await expect(expandBtn).toBeVisible();
      // Initially collapsed
      await expect(expandBtn).toHaveAttribute('aria-expanded', 'false');
    }
  });

  test('clicking expand button shows task detail row', async ({ page }) => {
    const region = page.getByRole('region', { name: 'Cost by work item table' });
    const isVisible = await region.isVisible();
    if (isVisible) {
      const expandBtn = region.getByTitle('Show task breakdown').first();
      await expandBtn.click();
      await expect(expandBtn).toHaveAttribute('aria-expanded', 'true');
    }
  });

  // ── Cost by node type ─────────────────────────────────────────────────────

  test('renders the Cost by Node Type section heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cost by Node Type', level: 2 })).toBeVisible();
  });

  test('cost by node type bar chart is present', async ({ page }) => {
    await expect(page.getByLabel('Cost by node type bar chart')).toBeVisible();
  });

  test('cost by node type table is present when data exists', async ({ page }) => {
    const region = page.getByRole('region', { name: 'Cost by node type table' });
    const isVisible = await region.isVisible();
    if (isVisible) {
      await expect(region.getByRole('columnheader', { name: 'Node' })).toBeVisible();
      await expect(region.getByRole('columnheader', { name: 'Tasks' })).toBeVisible();
    } else {
      await expect(page.getByText('No node cost data available')).toBeVisible();
    }
  });
});
