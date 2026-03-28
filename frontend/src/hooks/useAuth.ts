import { useDispatch, useSelector } from 'react-redux';
import type { RootState, AppDispatch } from '../store';
import { setCredentials, logout as logoutAction } from '../store/slices/authSlice';
import { login as loginApi, getMe } from '../api/auth';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

export function useAuth() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { user, isAuthenticated, isLoading, accessToken } = useSelector(
    (state: RootState) => state.auth
  );

  const login = async (email: string, password: string) => {
    const response = await loginApi(email, password);
    const { access_token } = response.data;
    dispatch(setCredentials({ accessToken: access_token }));
    const meResponse = await getMe();
    dispatch(setCredentials({ accessToken: access_token, user: meResponse.data }));
    navigate('/dashboard');
  };

  const logout = () => {
    dispatch(logoutAction());
    navigate('/login');
    toast.success('Logged out successfully');
  };

  return { user, isAuthenticated, isLoading, accessToken, login, logout };
}
