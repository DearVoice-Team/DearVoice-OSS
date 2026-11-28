import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Login from './Login'
import axiosInstance from '../apis/axiosInstance'
import { authStorage } from '../utils/authStorage'

const navigate = vi.fn()

vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => navigate,
}))

// 실제 Google 버튼 대신, 누르면 onSuccess / onError 를 부르는 가짜 버튼
vi.mock('@react-oauth/google', () => ({
  GoogleLogin: ({ onSuccess, onError }) => (
    <>
      <button onClick={() => onSuccess({ credential: 'google-id-token' })}>구글 로그인</button>
      <button onClick={() => onError()}>구글 로그인 취소</button>
    </>
  ),
}))

vi.mock('../apis/axiosInstance', () => ({
  default: { post: vi.fn() },
}))

const renderLogin = () =>
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )

// 입력창에 label 이 없어서 name 속성으로 찾는다.
const fillForm = async (user, id, pw) => {
  if (id) await user.type(document.querySelector('input[name="user_id"]'), id)
  if (pw) await user.type(document.querySelector('input[name="password"]'), pw)
}

describe('Login 페이지', () => {
  beforeEach(() => {
    navigate.mockReset()
    axiosInstance.post.mockReset()
  })

  it('로그인 폼을 보여준다', () => {
    renderLogin()
    expect(screen.getByText('아이디ㅣ')).toBeInTheDocument()
    expect(screen.getByText('비밀번호ㅣ')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '로그인' })).toBeInTheDocument()
  })

  it('빈 값으로 로그인하면 안내 모달을 띄우고 요청하지 않는다', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: '로그인' }))

    expect(screen.getByText('아이디와 비밀번호를 모두 입력해주세요.')).toBeInTheDocument()
    expect(axiosInstance.post).not.toHaveBeenCalled()
  })

  it('로그인에 성공하면 토큰을 저장하고 /home 으로 이동한다', async () => {
    const user = userEvent.setup()
    axiosInstance.post.mockResolvedValue({ data: { access: 'access-1', refresh: 'refresh-1' } })
    renderLogin()

    await fillForm(user, 'alice', 'Testpass!234')
    await user.click(screen.getByRole('button', { name: '로그인' }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/home'))
    expect(axiosInstance.post).toHaveBeenCalledWith(
      '/api/auth/login/',
      { user_id: 'alice', password: 'Testpass!234' },
      expect.anything(),
    )
    expect(authStorage.getAccessToken()).toBe('access-1')
    expect(authStorage.getRefreshToken()).toBe('refresh-1')
  })

  it('로그인에 실패하면 실패 모달을 띄운다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    axiosInstance.post.mockRejectedValue({ response: { status: 401 } })
    renderLogin()

    await fillForm(user, 'alice', 'wrong')
    await user.click(screen.getByRole('button', { name: '로그인' }))

    expect(await screen.findByText('아이디 또는 비밀번호를 확인해주세요.')).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalled()
    expect(authStorage.isLoggedIn()).toBe(false)

    await user.click(screen.getByRole('button', { name: '확인' }))
    expect(screen.queryByText('로그인 실패')).not.toBeInTheDocument()
  })

  it('구글 로그인에 성공하면 id_token 을 서버로 보내고 /home 으로 이동한다', async () => {
    const user = userEvent.setup()
    axiosInstance.post.mockResolvedValue({ data: { access: 'g-access', refresh: 'g-refresh' } })
    renderLogin()

    await user.click(screen.getByRole('button', { name: '구글 로그인' }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/home'))
    expect(axiosInstance.post).toHaveBeenCalledWith('/api/auth/login/google/', { id_token: 'google-id-token' })
    expect(authStorage.getAccessToken()).toBe('g-access')
  })

  it('구글 로그인이 취소되면 에러 메시지를 보여준다', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: '구글 로그인 취소' }))

    expect(screen.getByText('구글 로그인에 실패했습니다. 다시 시도해주세요.')).toBeInTheDocument()
  })

  it('회원가입 / 비밀번호 재설정 링크로 이동한다', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: '회원가입 바로가기' }))
    expect(navigate).toHaveBeenCalledWith('/signup')

    await user.click(screen.getByRole('button', { name: '비밀번호 재설정' }))
    expect(navigate).toHaveBeenCalledWith('/find-password')
  })
})
