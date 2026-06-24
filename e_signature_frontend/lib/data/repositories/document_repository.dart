import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/constants/api_constants.dart';
import '../../core/utils/session_manager.dart';
import '../models/document_model.dart';
import '../models/document_signature_summary_model.dart';
import '../models/document_signer_model.dart';


class DocumentRepository {
  final String _baseUrl = ApiConstants.baseUrl;

  Future<List<Document>> getDocuments({required String? token}) async {
    try {
      if (token == null) {
        throw Exception('Token JWT não encontrado.');
      }

      final response = await http.get(
        Uri.parse('$_baseUrl/documents'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      SessionManager.isUnauthorized(response.statusCode);

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => Document.fromJson(json)).toList();
      } else {
        throw Exception('Falha ao carregar os documentos. Código: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('Erro ao buscar documentos: $e');
      throw Exception('Erro ao buscar documentos.');
    }
  }

  Future<List<DocumentSigner>> getDocumentSigners() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('jwt_token');

    if (token == null) {
      throw Exception('Token JWT não encontrado.');
    }

    final response = await http.get(
      Uri.parse('$_baseUrl/document-signers'),
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
        'Falha ao carregar document_signers. Código: ${response.statusCode}',
      );
    }
  } catch (e) {
    debugPrint('Erro ao buscar document_signers: $e');
    throw Exception('Erro ao buscar status de assinatura.');
  }
}

  /// Cria um documento com um ou mais signatários (modelo paralelo).
  /// [signers] e [photos] devem estar na MESMA ordem (uma foto por signatário).
  Future<String?> createDocumentWithSigners({
    required int companyId,
    required String documentFileName,
    required Uint8List documentFileBytes,
    required List<Map<String, String>> signers,
    required List<({String name, Uint8List bytes})> photos,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('jwt_token');
      if (token == null) return 'Sessão expirada. Faça login novamente.';

      final dio = Dio();
      final formData = FormData.fromMap({
        'company_id': companyId,
        'signers': jsonEncode(signers),
        'document_file': MultipartFile.fromBytes(documentFileBytes, filename: documentFileName),
        'signer_photos': [
          for (final photo in photos)
            MultipartFile.fromBytes(photo.bytes, filename: photo.name),
        ],
      });

      // Cronometra o upload do PDF: do disparo do POST até o cliente receber
      // a resposta (201) — round-trip real percebido pelo usuário no upload.
      final uploadSw = Stopwatch()..start();
      final response = await dio.post(
        '$_baseUrl/documents',
        data: formData,
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
      uploadSw.stop();
      debugPrint(
        '[TEMPO] Upload do PDF (round-trip: POST /documents até status '
        '${response.statusCode}) levou ${uploadSw.elapsedMilliseconds} ms',
      );

      return response.statusCode == 201 ? null : 'Erro ao criar documento. Código: ${response.statusCode}';
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        SessionManager.handleUnauthorized();
        return 'Sessão expirada. Faça login novamente.';
      }
      final data = e.response?.data;
      if (data is Map && data['detail'] != null) return data['detail'].toString();
      debugPrint('Erro ao criar documento: ${e.message}');
      return 'Erro ao enviar documento. Tente novamente.';
    } catch (e) {
      debugPrint('Erro inesperado: $e');
      return 'Erro inesperado. Tente novamente.';
    }
  }

  Future<DocumentSignatureSummary?> getSignatureSummary({
    required int documentId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('jwt_token');

    if (token == null) {
      throw Exception('Token JWT não encontrado.');
    }

    final response = await http.get(
      Uri.parse('$_baseUrl/documents/$documentId/signature-summary'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
    );

    SessionManager.isUnauthorized(response.statusCode);

    if (response.statusCode == 200) {
      return DocumentSignatureSummary.fromJson(jsonDecode(response.body));
    }

    if (response.statusCode == 404) {
      return null;
    }

    throw Exception(
      'Falha ao buscar assinatura. Código: ${response.statusCode}',
    );
  }
}
