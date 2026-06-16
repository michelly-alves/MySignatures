// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:e_signature_frontend/core/constants/api_constants.dart';
import 'package:e_signature_frontend/core/utils/session_manager.dart';
import 'package:e_signature_frontend/data/models/document_model.dart';
import 'package:e_signature_frontend/data/repositories/auth_repository.dart';
import 'package:e_signature_frontend/data/services/crypto/document_crypto_signer.dart';
import 'package:e_signature_frontend/presentation/screens/documents/facial_recognition_screen.dart';
import 'package:e_signature_frontend/presentation/widgets/pdf_preview/pdf_preview.dart';
import 'package:e_signature_frontend/theme/app_colors.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class DocumentSignScreen extends StatefulWidget {
  final Document document;
  final bool allowSigning;

  const DocumentSignScreen({
    super.key,
    required this.document,
    this.allowSigning = true,
  });

  @override
  State<DocumentSignScreen> createState() => _DocumentSignScreenState();
}

class _DocumentSignScreenState extends State<DocumentSignScreen> {
  final AuthRepository _authRepository = AuthRepository();

  late final Future<Uint8List> _pdfFuture;
  bool _isSigning = false;
  bool _hasRegisteredKey = false;

  final ValueNotifier<bool> _pdfPointerEnabled = ValueNotifier(true);

  @override
  void initState() {
    super.initState();
    _pdfFuture = _loadPdf();
    if (widget.allowSigning) _loadKeyStatus();
  }

  @override
  void dispose() {
    _pdfPointerEnabled.dispose();
    super.dispose();
  }

  // ─── Carregamento do status da chave ───────────────────────────────────────

  Future<void> _loadKeyStatus() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('jwt_token');
      if (token == null) return;

      final response = await http.get(
        Uri.parse('${ApiConstants.baseUrl}/api/me'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (SessionManager.isUnauthorized(response.statusCode)) return;

      if (response.statusCode == 200 && mounted) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        setState(() => _hasRegisteredKey = data['has_signing_key'] == true);
      }
    } catch (_) {}
  }

  Future<Uint8List> _loadPdf() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('jwt_token');
    if (token == null || token.isEmpty) {
      throw Exception('Sessão expirada. Faça login novamente.');
    }

    final response = await http.get(
      Uri.parse('${ApiConstants.baseUrl}/documents/${widget.document.documentId}/file'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (SessionManager.isUnauthorized(response.statusCode)) {
      throw Exception('Sessão expirada. Faça login novamente.');
    }
    if (response.statusCode == 200) return response.bodyBytes;
    if (response.statusCode == 403) throw Exception('Sem permissão para visualizar este documento.');
    if (response.statusCode == 404) throw Exception('Arquivo do documento não encontrado.');
    throw Exception('Não foi possível carregar o PDF (${response.statusCode}).');
  }

  Future<String> _resolveDocumentHash(String token) async {
    final hash = widget.document.hashSha256;
    if (hash != null && hash.isNotEmpty) return hash;

    final response = await http.get(
      Uri.parse('${ApiConstants.baseUrl}/documents/${widget.document.documentId}'),
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
    );
    if (SessionManager.isUnauthorized(response.statusCode)) {
      throw Exception('Sessão expirada. Faça login novamente.');
    }
    if (response.statusCode != 200) throw Exception('Hash do documento indisponível.');

    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic>) throw Exception('Resposta inválida ao buscar documento.');

    final h = data['hash_sha256']?.toString();
    if (h == null || h.isEmpty) throw Exception('Hash do documento indisponível.');
    return h;
  }

  void _downloadFile(Uint8List bytes, String filename) {
    final blob = html.Blob([bytes]);
    final url = html.Url.createObjectUrlFromBlob(blob);
    html.AnchorElement(href: url)
      ..setAttribute('download', filename)
      ..click();
    html.Url.revokeObjectUrl(url);
  }

  Future<({Uint8List bytes, String name})?> _pickKeyFile() {
    final completer = Completer<({Uint8List bytes, String name})?>();
    final input = html.FileUploadInputElement()..accept = '.ekey';

    input.onChange.listen((_) {
      final file = input.files?.first;
      if (file == null) {
        if (!completer.isCompleted) completer.complete(null);
        return;
      }
      final reader = html.FileReader();
      reader.readAsArrayBuffer(file);
      reader.onLoad.listen((_) {
        if (!completer.isCompleted) {
          final raw = reader.result;
          final Uint8List bytes;
          if (raw is ByteBuffer) {
            bytes = raw.asUint8List();
          } else if (raw is Uint8List) {
            bytes = raw;
          } else {
            completer.completeError(Exception('Formato inesperado do arquivo.'));
            return;
          }
          completer.complete((bytes: bytes, name: file.name));
        }
      });
      reader.onError.listen((_) {
        if (!completer.isCompleted) completer.complete(null);
      });
    });

    input.click();
    return completer.future;
  }

  Future<bool> _showKeySetupDialog() async {
    final passwordCtrl = TextEditingController();
    final confirmCtrl  = TextEditingController();
    bool downloading = false;
    bool downloaded  = false;
    String? error;

    _pdfPointerEnabled.value = false;
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => Dialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Configurar Chave de Assinatura',
                      style: GoogleFonts.poppins(
                          fontSize: 17, fontWeight: FontWeight.bold, color: AppColors.primaryText)),
                  const SizedBox(height: 8),
                  Text(
                    'Crie uma senha para proteger sua chave privada. '
                    'Um arquivo .ekey será gerado — guarde-o com segurança. '
                    'Você precisará dele a cada assinatura.',
                    style: GoogleFonts.poppins(fontSize: 13, color: Colors.grey.shade700),
                  ),
                  const SizedBox(height: 20),
                  TextField(
                    controller: passwordCtrl,
                    obscureText: true,
                    decoration: InputDecoration(
                      labelText: 'Senha da chave',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: confirmCtrl,
                    obscureText: true,
                    decoration: InputDecoration(
                      labelText: 'Confirmar senha',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 8),
                    Text(error!, style: GoogleFonts.poppins(color: Colors.red, fontSize: 12)),
                  ],
                  const SizedBox(height: 20),
                  if (!downloaded)
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        icon: downloading
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.download_outlined),
                        label: Text(downloading ? 'Gerando...' : 'Gerar e Baixar Chave',
                            style: GoogleFonts.poppins(fontWeight: FontWeight.w600)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primaryButton,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: downloading
                            ? null
                            : () async {
                                // Senha usada SEM trim, idêntica ao fluxo de
                                // assinatura (_showSignDialog), para que a
                                // derivação PBKDF2 seja sempre consistente.
                                final pass    = passwordCtrl.text;
                                final confirm = confirmCtrl.text;
                                if (pass.length < 8) {
                                  setLocal(() => error = 'Senha deve ter pelo menos 8 caracteres.');
                                  return;
                                }
                                if (pass != confirm) {
                                  setLocal(() => error = 'As senhas não coincidem.');
                                  return;
                                }
                                setLocal(() { downloading = true; error = null; });

                                try {
                                  final result = await DocumentCryptoSigner()
                                      .generateAndEncryptKeyPair(pass);

                                  final ok = await _authRepository
                                      .registerSigningKey(result.publicKeyPem);
                                  if (!ok) throw Exception('Falha ao registrar chave no servidor.');

                                  _downloadFile(
                                    result.encryptedKeyFile,
                                    'chave-assinatura-${widget.document.documentId}.ekey',
                                  );
                                  setLocal(() { downloaded = true; downloading = false; });
                                } catch (e) {
                                  setLocal(() {
                                    error = e.toString().replaceFirst('Exception: ', '');
                                    downloading = false;
                                  });
                                }
                              },
                      ),
                    )
                  else ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.check_circle_outline, color: Colors.green, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Arquivo .ekey baixado e chave registrada com sucesso.',
                              style: GoogleFonts.poppins(fontSize: 13, color: Colors.green.shade800),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => Navigator.pop(ctx, true),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primaryButton,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        child: Text('Continuar para assinar',
                            style: GoogleFonts.poppins(fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Center(
                    child: TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: Text('Cancelar', style: GoogleFonts.poppins(color: Colors.grey)),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    _pdfPointerEnabled.value = true;
    return result == true;
  }

  /// Diálogo de assinatura: seleciona arquivo .ekey + senha + confirmação.
  Future<({Uint8List keyFile, String password})?> _showSignDialog() async {
    Uint8List? keyFile;
    String keyFileName = '';
    final passwordCtrl = TextEditingController();
    bool loadingFile = false;
    String? error;

    _pdfPointerEnabled.value = false;
    final result = await showDialog<({Uint8List keyFile, String password})>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => Dialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Assinar Documento',
                      style: GoogleFonts.poppins(
                          fontSize: 17, fontWeight: FontWeight.bold, color: AppColors.primaryText)),
                  const SizedBox(height: 8),
                  Text(
                    'Ao assinar "${widget.document.fileName}", você declara ter lido '
                    'e concordado com o conteúdo. Esta ação não pode ser desfeita.',
                    style: GoogleFonts.poppins(fontSize: 13, color: Colors.grey.shade700),
                  ),
                  const SizedBox(height: 20),

                  // Seletor de arquivo
                  OutlinedButton.icon(
                    icon: loadingFile
                        ? const SizedBox(
                            width: 16, height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : Icon(
                            keyFile != null ? Icons.check_circle_outline : Icons.upload_file,
                            color: keyFile != null ? Colors.green : AppColors.primaryButton,
                          ),
                    label: Text(
                      keyFile != null ? keyFileName : 'Selecionar arquivo .ekey',
                      style: GoogleFonts.poppins(
                        color: keyFile != null ? Colors.green.shade700 : AppColors.primaryButton,
                        fontSize: 13,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: BorderSide(
                          color: keyFile != null ? Colors.green : AppColors.primaryButton),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    ),
                    onPressed: loadingFile
                        ? null
                        : () async {
                            setLocal(() { loadingFile = true; error = null; });
                            try {
                              final picked = await _pickKeyFile();
                              if (picked != null) {
                                setLocal(() {
                                  keyFile = picked.bytes;
                                  keyFileName = picked.name;
                                });
                              }
                            } finally {
                              setLocal(() => loadingFile = false);
                            }
                          },
                  ),

                  const SizedBox(height: 12),
                  TextField(
                    controller: passwordCtrl,
                    obscureText: true,
                    onChanged: (_) => setLocal(() {}),
                    decoration: InputDecoration(
                      labelText: 'Senha da chave',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),

                  if (error != null) ...[
                    const SizedBox(height: 8),
                    Text(error!, style: GoogleFonts.poppins(color: Colors.red, fontSize: 12)),
                  ],

                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton(
                      onPressed: () {
                        Navigator.pop(ctx);
                        _rotateKey();
                      },
                      style: TextButton.styleFrom(padding: EdgeInsets.zero),
                      child: Text(
                        'Perdi minha chave de assinatura',
                        style: GoogleFonts.poppins(
                          fontSize: 12,
                          color: AppColors.primaryButton,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: () => Navigator.pop(ctx),
                        child: Text('Cancelar', style: GoogleFonts.poppins(color: Colors.grey)),
                      ),
                      const SizedBox(width: 8),
                      ElevatedButton(
                        onPressed: (keyFile == null || passwordCtrl.text.isEmpty)
                            ? null
                            : () => Navigator.pop(ctx,
                                (keyFile: keyFile!, password: passwordCtrl.text)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primaryButton,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        child: Text('Assinar',
                            style: GoogleFonts.poppins(fontWeight: FontWeight.w600)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    _pdfPointerEnabled.value = true;
    return result;
  }

  /// Fluxo de rotação de chave (perda do .ekey/senha): captura selfie para
  /// re-verificação facial no servidor, gera um novo par de chaves e
  /// substitui a âncora de identidade.
  Future<void> _rotateKey() async {
    final image = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (_) => const FacialRecognitionScreen(
          userId: '',
          captureOnly: true,
        ),
      ),
    );
    if (image == null || !mounted) return;

    await _showKeyRotationDialog(image);
  }

  Future<void> _showKeyRotationDialog(String liveImageBase64) async {
    final passwordCtrl = TextEditingController();
    final confirmCtrl = TextEditingController();
    bool processing = false;
    bool done = false;
    String? error;

    _pdfPointerEnabled.value = false;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => Dialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Rotacionar Chave de Assinatura',
                      style: GoogleFonts.poppins(
                          fontSize: 17, fontWeight: FontWeight.bold, color: AppColors.primaryText)),
                  const SizedBox(height: 8),
                  Text(
                    'Sua identidade foi verificada por reconhecimento facial. '
                    'Crie uma senha para a NOVA chave. A chave anterior será '
                    'revogada — assinaturas já feitas continuam válidas.',
                    style: GoogleFonts.poppins(fontSize: 13, color: Colors.grey.shade700),
                  ),
                  const SizedBox(height: 20),
                  if (!done) ...[
                    TextField(
                      controller: passwordCtrl,
                      obscureText: true,
                      decoration: InputDecoration(
                        labelText: 'Nova senha da chave',
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: confirmCtrl,
                      obscureText: true,
                      decoration: InputDecoration(
                        labelText: 'Confirmar nova senha',
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 8),
                      Text(error!, style: GoogleFonts.poppins(color: Colors.red, fontSize: 12)),
                    ],
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        icon: processing
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.autorenew),
                        label: Text(processing ? 'Rotacionando...' : 'Gerar nova chave',
                            style: GoogleFonts.poppins(fontWeight: FontWeight.w600)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primaryButton,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: processing
                            ? null
                            : () async {
                                final pass = passwordCtrl.text;
                                final confirm = confirmCtrl.text;
                                if (pass.length < 8) {
                                  setLocal(() => error = 'Senha deve ter pelo menos 8 caracteres.');
                                  return;
                                }
                                if (pass != confirm) {
                                  setLocal(() => error = 'As senhas não coincidem.');
                                  return;
                                }
                                setLocal(() { processing = true; error = null; });
                                try {
                                  final keyResult = await DocumentCryptoSigner()
                                      .generateAndEncryptKeyPair(pass);

                                  final rotation = await _authRepository.rotateSigningKey(
                                    keyResult.publicKeyPem,
                                    liveImageBase64,
                                  );
                                  if (!rotation.ok) {
                                    throw Exception(
                                        rotation.error ?? 'Falha ao rotacionar a chave.');
                                  }

                                  _downloadFile(
                                    keyResult.encryptedKeyFile,
                                    'chave-assinatura-${widget.document.documentId}.ekey',
                                  );
                                  setLocal(() { done = true; processing = false; });
                                } catch (e) {
                                  setLocal(() {
                                    error = e.toString().replaceFirst('Exception: ', '');
                                    processing = false;
                                  });
                                }
                              },
                      ),
                    ),
                    const SizedBox(height: 8),
                    Center(
                      child: TextButton(
                        onPressed: () => Navigator.pop(ctx),
                        child: Text('Cancelar', style: GoogleFonts.poppins(color: Colors.grey)),
                      ),
                    ),
                  ] else ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.check_circle_outline, color: Colors.green, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Nova chave gerada e registrada. O novo arquivo .ekey '
                              'foi baixado — guarde-o com segurança.',
                              style: GoogleFonts.poppins(fontSize: 13, color: Colors.green.shade800),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => Navigator.pop(ctx),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primaryButton,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        child: Text('Concluir',
                            style: GoogleFonts.poppins(fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
    _pdfPointerEnabled.value = true;
  }

  Future<void> _signDocument() async {
    // Primeiro acesso: configura chave persistente
    if (!_hasRegisteredKey) {
      final setupOk = await _showKeySetupDialog();
      if (!setupOk) return;
      if (mounted) setState(() => _hasRegisteredKey = true);
    }

    // Carrega arquivo + senha
    final signInput = await _showSignDialog();
    if (signInput == null) return;

    setState(() => _isSigning = true);
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('jwt_token');
      if (token == null || token.isEmpty) {
        throw Exception('Sessão expirada. Faça login novamente.');
      }

      final documentHash = await _resolveDocumentHash(token);

      final signature = await DocumentCryptoSigner().signDocumentHash(
        documentHash,
        signInput.keyFile,
        signInput.password,
      );

      final response = await http.post(
        Uri.parse('${ApiConstants.baseUrl}/documents/${widget.document.documentId}/sign'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'signature_base64': signature.signatureBase64,
          'public_key_pem': signature.publicKeyPem,
        }),
      );

      if (!mounted) return;

      if (SessionManager.isUnauthorized(response.statusCode)) return;

      if (response.statusCode == 201) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: Colors.green,
          content: Text('Documento assinado e registrado com sucesso.'),
        ));
        Navigator.of(context).pop();
        return;
      }

      String message = 'Não foi possível assinar o documento.';
      try {
        final data = jsonDecode(response.body);
        if (data is Map<String, dynamic> && data['detail'] != null) {
          message = data['detail'].toString();
        }
      } catch (_) {
        message = '$message Código: ${response.statusCode}';
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(backgroundColor: Colors.redAccent, content: Text(message)),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text(e.toString().replaceFirst('Exception: ', '')),
      ));
    } finally {
      if (mounted) setState(() => _isSigning = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: AppColors.primaryText),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          widget.document.fileName,
          overflow: TextOverflow.ellipsis,
          style: GoogleFonts.poppins(color: AppColors.primaryText, fontWeight: FontWeight.w600),
        ),
      ),
      body: FutureBuilder<Uint8List>(
        future: _pdfFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  snapshot.error.toString().replaceFirst('Exception: ', ''),
                  textAlign: TextAlign.center,
                  style: GoogleFonts.poppins(color: Colors.red.shade700, fontSize: 15),
                ),
              ),
            );
          }
          final pdfBytes = snapshot.data;
          if (pdfBytes == null || pdfBytes.isEmpty) {
            return Center(child: Text('PDF vazio ou indisponível.',
                style: GoogleFonts.poppins(fontSize: 15)));
          }
          return SizedBox.expand(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: ColoredBox(
                  color: Colors.white,
                  child: PdfPreview(
                    bytes: pdfBytes,
                    fileName: widget.document.fileName,
                    pointerEventsNotifier: _pdfPointerEnabled,
                  ),
                ),
              ),
            ),
          );
        },
      ),
      bottomNavigationBar: widget.allowSigning
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: ElevatedButton.icon(
                  onPressed: _isSigning ? null : _signDocument,
                  icon: _isSigning
                      ? const SizedBox(
                          width: 18, height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.draw_outlined),
                  label: Text(
                    _isSigning ? 'Assinando...' : 'Assinar Documento',
                    style: GoogleFonts.poppins(fontWeight: FontWeight.w600),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primaryButton,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
            )
          : null,
    );
  }
}
