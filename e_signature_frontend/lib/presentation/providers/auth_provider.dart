import 'package:flutter/material.dart';
import '../../data/repositories/auth_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';
class AuthProvider extends ChangeNotifier {
  final AuthRepository _authRepository = AuthRepository();

  String? _token;
  String? get token => _token;

  Map<String, dynamic>? _user;
  Map<String, dynamic>? get user => _user;

  bool _isAuthenticated = false;
  bool get isAuthenticated => _isAuthenticated;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  bool _isAuthCheckComplete = false;
  bool get isAuthCheckComplete => _isAuthCheckComplete;
  bool get isActive => _user?['is_active'];
  bool get requiresOtpVerification => _user?['requires_otp_verification'] == true;

  int? get companyId => _user?['company_id'];
  int? get userId => _user?['user_id'];
  String? get userEmail => _user?['email'];


  AuthProvider() {
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('jwt_token');

    if (_token != null) {
      final user = await _authRepository.getCurrentUser();
      if (user != null) {
        _user = user;
        _isAuthenticated = true;
      } else {
        await prefs.remove('jwt_token');
        _token = null;
      }
    }

    _isAuthCheckComplete = true;
    notifyListeners();
  }

  Future<bool> login(String email, String password) async {
    _isLoading = true;
    notifyListeners();

    final prefs = await SharedPreferences.getInstance();

    final token = await _authRepository.signIn(
      email: email,
      password: password,
    );

    if (token == null) {
      _isLoading = false;
      notifyListeners();
      return false;
    }

    await prefs.setString('jwt_token', token);
    _token = token;

    final user = await _authRepository.getCurrentUser();
    if (user == null) {
      _isLoading = false;
      notifyListeners();
      return false;
    }

    _user = user;
    _isAuthenticated = true;

    _isLoading = false;
    notifyListeners();
    return true;
  }

  Future<bool> generateOtpForCurrentUser() {
    return _authRepository.generateOtpForCurrentUser();
  }

  Future<void> refreshCurrentUser() async {
    final user = await _authRepository.getCurrentUser();
    if (user != null) {
      _user = user;
      _isAuthenticated = true;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('jwt_token');

    _token = null;
    _user = null;
    _isAuthenticated = false;

    notifyListeners();
  }
}
