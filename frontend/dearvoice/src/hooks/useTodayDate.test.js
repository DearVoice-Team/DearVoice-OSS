import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTodayDate } from './useTodayDate'

describe('useTodayDate', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('오늘 날짜를 YYYYMMDD 형식으로 돌려준다', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 0, 5, 9, 30))

    const { result } = renderHook(() => useTodayDate())

    expect(result.current).toBe('20260105')
  })
})
