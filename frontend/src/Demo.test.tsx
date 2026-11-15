import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { Demo } from './Demo';

describe('public demo', () => {
  it('labels synthetic data and navigates to case evidence', async () => {
    window.location.hash = '';
    render(<Demo />);
    expect(screen.getByText(/合成示例数据/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByText('查看详情')[0]);
    expect(screen.getByText('案件详情与时间线')).toBeInTheDocument();
    await userEvent.click(screen.getByText('查看风险与证据'));
    expect(screen.getByText('风险结果与原文证据')).toBeInTheDocument();
  });
});
