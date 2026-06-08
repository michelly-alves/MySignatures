class ApiConstants {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String signupEndpoint = '/auth/login';
  static const String createUser = '/api/users';
  static const String documents = '/documents';
}
