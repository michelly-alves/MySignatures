import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/constants/api_constants.dart';
import '../../core/utils/session_manager.dart';
import '../models/document_signer_model.dart';

class DocumentSignerRepository {
  final String _baseUrl = ApiConstants.baseUrl;

  Future<List<DocumentSigner>> getDocumentSigners({
    int? documentId,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('jwt_token');

      if (token == null) {
        throw Exception('Token JWT não encontrado.');
      }

      String url = '$_baseUrl/document-signers';

      if (documentId != null) {
        url += '?document_id=$documentId';
      }

      final response = await http.get(
        Uri.parse(url),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      SessionManager.isUnauthorized(response.statusCode);

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);

        return data
            .map((json) => DocumentSigner.fromJson(json))
            .toList();
      } else {
        throw Exception(
            'Erro ao buscar document signers (${response.statusCode})');
      }
    } catch (e) {
      debugPrint('Erro repository document signer: $e');
      rethrow;
    }
  }

Future<String?> replaceSignerPhoto({
    required int documentId,
    required int signerId,
    required String fileName,
    required Uint8List bytes,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('jwt_token');
      if (token == null) return 'Sessão expirada. Faça login novamente.';

      final uri = Uri.parse(
          '$_baseUrl/documents/$documentId/signers/$signerId/photo');
      final request = http.MultipartRequest('PUT', uri)
        ..headers['Authorization'] = 'Bearer $token'
        ..files.add(http.MultipartFile.fromBytes(
          'photo_file',
          bytes,
          filename: fileName,
        ));

      final streamed = await request.send();
      final response = await http.Response.fromStream(streamed);
      SessionManager.isUnauthorized(response.statusCode);

      if (response.statusCode == 200) return null;

      try {
        final data = jsonDecode(response.body);
        if (data is Map && data['detail'] != null) {
          return data['detail'].toString();
        }
      } catch (_) {}
      return 'Erro ao atualizar a foto (${response.statusCode}).';
    } catch (e) {
      debugPrint('Erro replaceSignerPhoto: $e');
      return 'Erro inesperado ao atualizar a foto.';
    }
  }
}
