import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:developer';

import '../../core/constants/api_constants.dart';
import '../../core/utils/session_manager.dart';

class AuthRepository {
  final String _baseUrl = ApiConstants.baseUrl;

   Future<String?> signIn({
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/auth/login'),
      headers: {
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'email': email,
        'password': password,
      }),
    );

    log('LOGIN STATUS: ${response.statusCode}');
    log('LOGIN BODY: ${response.body}');

    if (response.statusCode != 200) {
      return null;
    }

    final Map<String, dynamic> data = jsonDecode(response.body);

    return data['access_token'] as String?;
  }


  Future<Map<String, dynamic>?> getCurrentUser() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString("jwt_token");

    if (token == null) return null;

    final uri = Uri.parse("$_baseUrl/api/me");

    final response = await http.get(
      uri,
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer $token",
      },
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }

    log("Erro ao obter usuário atual: ${response.statusCode} ${response.body}");
    return null;
  }

  Future<bool> generateOtpForCurrentUser() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString("jwt_token");

    if (token == null) return false;

    final response = await http.post(
      Uri.parse('$_baseUrl/otp/generate/current'),
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer $token",
      },
    );

    if (SessionManager.isUnauthorized(response.statusCode)) return false;

    if (response.statusCode == 200) {
      return true;
    }

    log("Erro ao gerar OTP: ${response.statusCode} ${response.body}");
    return false;
  }

  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('jwt_token');
  }

  Future<void> signOut() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('jwt_token');
  }

  Future<bool> verifyFace(String imageBase64, String userId) async {
    final url = Uri.parse('$_baseUrl/face-verification/face-verify/$userId');
    final token = await getToken();

    if (token == null) return false;

    try {
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: json.encode({'live_image_base64': imageBase64}),
      );

      if (SessionManager.isUnauthorized(response.statusCode)) return false;

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return data['verified'] ?? false;
      } else {
        log('Falha na verificação facial: ${response.statusCode} - ${response.body}');
        return false;
      }
    } catch (e) {
      log('Erro na chamada da API: $e');
      return false;
    }
  }

  Future<bool> verifyDocumentLiveness({
    required int documentId,
    required Map<String, String> frames,
  }) async {
    final token = await getToken();
    if (token == null) return false;

    final response = await http.post(
      Uri.parse('$_baseUrl/face-verification/documents/$documentId/liveness-check'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({
        'frames': frames.entries
            .map((entry) => {
                  'step': entry.key,
                  'image_base64': entry.value,
                })
            .toList(),
      }),
    );

    if (SessionManager.isUnauthorized(response.statusCode)) return false;

    if (response.statusCode != 200) {
      log('Falha na prova de vida: ${response.statusCode} ${response.body}');
      return false;
    }

    final data = jsonDecode(response.body);
    return data['verified'] == true;
  }

  Future<bool> requestPasswordReset(String email) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/auth/forgot-password'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email}),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Erro ao solicitar reset de senha: $e');
      return false;
    }
  }

  Future<String?> createUser(Map<String, dynamic> userData) async {
    final url = Uri.parse('$_baseUrl/api/users');

    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(userData),
      );

      if (response.statusCode == 201) return null;

      try {
        final data = jsonDecode(response.body);
        if (data is Map<String, dynamic> && data['detail'] != null) {
          return data['detail'].toString();
        }
      } catch (_) {}
      return 'Erro ao cadastrar. Código: ${response.statusCode}';
    } catch (e) {
      log('Erro ao criar usuário: $e');
      return 'Erro de conexão. Verifique sua internet.';
    }
  }
  
  Future<bool> registerSigningKey(String publicKeyPem) async {
    final token = await getToken();
    if (token == null) return false;

    final response = await http.put(
      Uri.parse('$_baseUrl/api/signer/public-key'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({'public_key_pem': publicKeyPem}),
    );

    if (SessionManager.isUnauthorized(response.statusCode)) return false;

    return response.statusCode == 200;
  }

  Future<({bool ok, String? error})> rotateSigningKey(
    String newPublicKeyPem,
    String liveImageBase64,
  ) async {
    final token = await getToken();
    if (token == null) return (ok: false, error: 'Sessão expirada.');

    final response = await http.post(
      Uri.parse('$_baseUrl/api/signer/rotate-key'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({
        'new_public_key_pem': newPublicKeyPem,
        'live_image_base64': liveImageBase64,
      }),
    );

    if (SessionManager.isUnauthorized(response.statusCode)) {
      return (ok: false, error: 'Sessão expirada. Faça login novamente.');
    }

    if (response.statusCode == 200) return (ok: true, error: null);

    String msg = 'Falha ao rotacionar a chave (código ${response.statusCode}).';
    try {
      final data = jsonDecode(response.body);
      if (data is Map && data['detail'] != null) msg = data['detail'].toString();
    } catch (_) {}
    return (ok: false, error: msg);
  }

  Future<({bool ok, String? error})> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final token = await getToken();
    if (token == null) return (ok: false, error: 'Sessão expirada.');

    final response = await http.post(
      Uri.parse('$_baseUrl/auth/change-password'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({
        'current_password': currentPassword,
        'new_password': newPassword,
      }),
    );

    if (SessionManager.isUnauthorized(response.statusCode)) {
      return (ok: false, error: 'Sessão expirada. Faça login novamente.');
    }

    if (response.statusCode == 200) return (ok: true, error: null);

    String msg = 'Falha ao alterar a senha (código ${response.statusCode}).';
    try {
      final data = jsonDecode(response.body);
      final detail = data is Map ? data['detail'] : null;
      if (detail is String) {
        msg = detail;
      } else if (detail is List && detail.isNotEmpty && detail.first is Map) {
        msg = (detail.first['msg'] ?? msg)
            .toString()
            .replaceFirst('Value error, ', '');
      }
    } catch (_) {}
    return (ok: false, error: msg);
  }

  Future<bool> updateUser(int userId, Map<String, dynamic> data) async {
  final token = await getToken();
  if (token == null) return false;

  final response = await http.put(
    Uri.parse('$_baseUrl/api/users/$userId'),
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    },
    body: jsonEncode(data),
  );

  if (SessionManager.isUnauthorized(response.statusCode)) return false;

  return response.statusCode == 200;
}
}
