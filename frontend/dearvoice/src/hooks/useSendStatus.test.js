import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useSendStatus } from './useSendStatus'

describe('useSendStatus', () => {
  it('전송이 성공하면 isSent 가 true 가 된다', async () => {
    const { result } = renderHook(() => useSendStatus())

    await act(() => result.current.handleSend(async () => true))

    expect(result.current.isSent).toBe(true)
    expect(result.current.isSending).toBe(false)
  })

  it('전송 함수가 false 를 돌려주면 전송 완료로 보지 않는다', async () => {
    const { result } = renderHook(() => useSendStatus())
    await act(() => result.current.handleSend(async () => false))
    expect(result.current.isSent).toBe(false)
  })

  it('전송 중 에러가 나도 isSending 을 되돌린다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { result } = renderHook(() => useSendStatus())

    await act(() => result.current.handleSend(async () => { throw new Error('network') }))

    expect(result.current.isSent).toBe(false)
    expect(result.current.isSending).toBe(false)
  })

  it('전송 중에는 isSending 이 true 이다', async () => {
    const { result } = renderHook(() => useSendStatus())
    let finish
    const pending = new Promise((resolve) => { finish = resolve })

    let sendPromise
    act(() => { sendPromise = result.current.handleSend(() => pending) })
    expect(result.current.isSending).toBe(true)

    await act(async () => { finish(true); await sendPromise })
    expect(result.current.isSending).toBe(false)
  })

  it('resetStatus 로 초기화한다', async () => {
    const { result } = renderHook(() => useSendStatus())
    await act(() => result.current.handleSend(async () => true))
    act(() => result.current.resetStatus())
    expect(result.current.isSent).toBe(false)
  })
})
