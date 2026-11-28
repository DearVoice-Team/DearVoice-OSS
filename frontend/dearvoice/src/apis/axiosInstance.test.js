import axios from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axiosInstance from './axiosInstance'
import { authStorage } from '../utils/authStorage'

const originalAdapter = axiosInstance.defaults.adapter

afterEach(() => {
  axiosInstance.defaults.adapter = originalAdapter
})

/**
 * 실제 서버 대신 axios adapter 를 바꿔서 요청을 가로챈다.
 * handler(config) 가 돌려준 status 로 응답한다.
 */
const mockServer = (handler) => {
  const requests = []
  axiosInstance.defaults.adapter = async (config) => {
    requests.push(config)
    const { status = 200, data = {} } = handler(config, requests.length) ?? {}
    const response = { status, data, headers: {}, config, statusText: String(status) }
    if (status >= 400) {
      const error = new Error(`Request failed with status code ${status}`)
      error.config = config
      error.response = response
      error.isAxiosError = true
      throw error
    }
    return response
  }
  return requests
}

const authHeader = (config) => config.headers?.Authorization ?? config.headers?.get?.('Authorization')

describe('axiosInstance 요청 인터셉터', () => {
  beforeEach(() => {
    authStorage.setTokens('access-1', 'refresh-1')
  })

  it('일반 API 요청에는 Bearer 토큰을 붙인다', async () => {
    const requests = mockServer(() => ({ data: { ok: true } }))
    await axiosInstance.get('/api/letters/list/')
    expect(authHeader(requests[0])).toBe('Bearer access-1')
  })

  it.each(['/api/auth/login/', '/api/auth/signup/', '/api/auth/refresh/', '/api/auth/login/google/'])(
    '%s 요청에는 토큰을 붙이지 않는다',
    async (url) => {
      const requests = mockServer(() => ({}))
      await axiosInstance.post(url, {})
      expect(authHeader(requests[0])).toBeUndefined()
    },
  )
})

describe('axiosInstance 응답 인터셉터 (토큰 재발급)', () => {
  beforeEach(() => {
    authStorage.setTokens('expired-access', 'refresh-1')
    // jsdom 은 페이지 이동을 지원하지 않아서 생기는 콘솔 에러를 숨긴다.
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('401 이면 refresh 토큰으로 access 를 재발급받고 원래 요청을 다시 보낸다', async () => {
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access: 'new-access' } })
    const requests = mockServer((config, n) => (n === 1 ? { status: 401 } : { data: { ok: true } }))

    const res = await axiosInstance.get('/api/auth/me/')

    expect(res.data).toEqual({ ok: true })
    expect(refresh).toHaveBeenCalledWith(expect.stringContaining('/api/auth/refresh/'), { refresh: 'refresh-1' })
    expect(authStorage.getAccessToken()).toBe('new-access')
    expect(requests).toHaveLength(2)
    expect(authHeader(requests[1])).toBe('Bearer new-access')
  })

  it('재발급도 실패하면 토큰을 지운다', async () => {
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh expired'))
    mockServer(() => ({ status: 401 }))

    await expect(axiosInstance.get('/api/auth/me/')).rejects.toBeTruthy()
    expect(authStorage.getAccessToken()).toBeNull()
    expect(authStorage.getRefreshToken()).toBeNull()
  })

  it('로그인 요청의 401 은 재발급을 시도하지 않는다', async () => {
    const refresh = vi.spyOn(axios, 'post')
    mockServer(() => ({ status: 401 }))

    await expect(axiosInstance.post('/api/auth/login/', {})).rejects.toBeTruthy()
    expect(refresh).not.toHaveBeenCalled()
    expect(authStorage.getRefreshToken()).toBe('refresh-1')
  })

  it('401 이 아닌 에러는 그대로 돌려준다', async () => {
    mockServer(() => ({ status: 500 }))
    await expect(axiosInstance.get('/api/letters/list/')).rejects.toMatchObject({ response: { status: 500 } })
    expect(authStorage.getAccessToken()).toBe('expired-access')
  })
})
