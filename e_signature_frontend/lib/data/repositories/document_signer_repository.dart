import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/constants/api_constants.dart';
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
}
