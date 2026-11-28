import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import ProtectedRoute from './ProtectedRoute'
import { authStorage } from '../utils/authStorage'

const renderAt = (path) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>로그인 페이지</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/home" element={<div>홈 화면</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

describe('ProtectedRoute', () => {
  it('토큰이 없으면 /login 으로 보낸다', () => {
    renderAt('/home')
    expect(screen.getByText('로그인 페이지')).toBeInTheDocument()
    expect(screen.queryByText('홈 화면')).not.toBeInTheDocument()
  })

  it('access 토큰이 있으면 보호된 화면을 보여준다', () => {
    authStorage.setAccessToken('access-1')
    renderAt('/home')
    expect(screen.getByText('홈 화면')).toBeInTheDocument()
  })

  it('refresh 토큰만 있어도 보호된 화면을 보여준다 (access 는 재발급)', () => {
    authStorage.setRefreshToken('refresh-1')
    renderAt('/home')
    expect(screen.getByText('홈 화면')).toBeInTheDocument()
  })
})
