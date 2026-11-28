import { describe, expect, it } from 'vitest'
import { authStorage } from './authStorage'

describe('authStorage', () => {
  it('토큰이 없으면 로그인 상태가 아니다', () => {
    expect(authStorage.isLoggedIn()).toBe(false)
    expect(authStorage.hasRefreshToken()).toBe(false)
    expect(authStorage.getAccessToken()).toBeNull()
  })

  it('setTokens 로 access / refresh 토큰을 함께 저장한다', () => {
    authStorage.setTokens('access-1', 'refresh-1')

    expect(authStorage.getAccessToken()).toBe('access-1')
    expect(authStorage.getRefreshToken()).toBe('refresh-1')
    expect(authStorage.isLoggedIn()).toBe(true)
    expect(authStorage.hasRefreshToken()).toBe(true)
  })

  it('refresh 토큰 없이 setTokens 하면 기존 refresh 토큰을 유지한다', () => {
    authStorage.setTokens('access-1', 'refresh-1')
    authStorage.setTokens('access-2')

    expect(authStorage.getAccessToken()).toBe('access-2')
    expect(authStorage.getRefreshToken()).toBe('refresh-1')
  })

  it('토큰을 하나씩 지울 수 있다', () => {
    authStorage.setTokens('access-1', 'refresh-1')

    authStorage.removeAccessToken()
    expect(authStorage.isLoggedIn()).toBe(false)
    expect(authStorage.hasRefreshToken()).toBe(true)

    authStorage.removeRefreshToken()
    expect(authStorage.hasRefreshToken()).toBe(false)
  })

  it('clearTokens 로 로그아웃한다', () => {
    authStorage.setAccessToken('access-1')
    authStorage.setRefreshToken('refresh-1')

    authStorage.clearTokens()

    expect(authStorage.getAccessToken()).toBeNull()
    expect(authStorage.getRefreshToken()).toBeNull()
  })
})
