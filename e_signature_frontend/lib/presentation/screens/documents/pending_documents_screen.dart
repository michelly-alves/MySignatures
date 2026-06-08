import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'dart:developer';

import '../../../data/repositories/document_repository.dart';
import '../../../data/repositories/document_signer_repository.dart';
import '../../../data/models/document_model.dart';
import '../../../data/models/document_signer_model.dart';
import '../../providers/auth_provider.dart';
import '../../../theme/app_colors.dart';
import 'facial_recognition_screen.dart';

class PendingDocumentsScreen extends StatefulWidget {
  const PendingDocumentsScreen({super.key});

  @override
  State<PendingDocumentsScreen> createState() =>
      _PendingDocumentsScreenState();
}

class _PendingDocumentsScreenState extends State<PendingDocumentsScreen> {
  late Future<List<Document>> _documentsFuture;
  late Future<List<DocumentSigner>> _signersFuture;

  bool _fetchInitiated = false;

  static const int documentCreated = 1;
  static const int documentInProgress = 2;
  static const int identityVerified = 2;

  bool _isPendingForSignature(Document document) {
    return document.statusId == documentCreated ||
        document.statusId == documentInProgress;
  }

  void _initiateFetch(String token) {
    if (_fetchInitiated) return;
    _fetchInitiated = true;

    _documentsFuture = DocumentRepository().getDocuments(token: token);
    _signersFuture = DocumentSignerRepository().getDocumentSigners();
  }

  Widget _pendingBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        "Pendente",
        style: GoogleFonts.poppins(
          color: Colors.orange.shade700,
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
      ),
    );
  }

  Future<void> _openDocument(
      Document doc,
      DocumentSigner? signer,
      AuthProvider auth,
      ) async {
    final user = auth.user;

    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);

    if (user == null || user['is_active'] != true) {
      messenger.showSnackBar(
        const SnackBar(content: Text("Conta inativa. Assinatura bloqueada.")),
      );
      return;
    }

    if (signer == null) {
      messenger.showSnackBar(
        const SnackBar(content: Text("Vínculo de assinatura não encontrado.")),
      );
      return;
    }

    if (signer.statusId != identityVerified) {
      final verified = await navigator.push<bool>(
        MaterialPageRoute(
          builder: (_) => FacialRecognitionScreen(
            userId: user['user_id'].toString(),
            documentId: doc.documentId,
          ),
        ),
      );

      if (!mounted) return;

      if (verified != true) {
        messenger.showSnackBar(
          const SnackBar(
            content: Text("Realize a verificação de identidade antes de assinar."),
          ),
        );
        return;
      }
    }

    log("Abrindo documento ${doc.fileName}");

    if (!mounted) return;

    await navigator.pushNamed("/document-sign", arguments: doc);

    if (mounted) {
      setState(() => _fetchInitiated = false);
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
          icon:
              const Icon(Icons.arrow_back_ios, color: AppColors.primaryText),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          'Documentos Pendentes',
          style: GoogleFonts.poppins(
            color: AppColors.primaryText,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      body: Consumer<AuthProvider>(
        builder: (context, auth, child) {
          if (!auth.isAuthCheckComplete) {
            return const Center(child: CircularProgressIndicator());
          }

          if (!auth.isAuthenticated) {
            return const Center(
              child: Text('Sessão expirada. Faça login novamente.'),
            );
          }

          final user = auth.user;

        if (user == null || user['is_active'] != true){
            return Center(
              child: Text(
                "Sua conta está inativa.",
                style: GoogleFonts.poppins(color: Colors.red),
              ),
            );
          }

          if (user['role'] != 2) {
            return const Center(
              child: Text('Assinaturas pendentes são exibidas apenas para signatários.'),
            );
          }

          _initiateFetch(auth.token!);

          return FutureBuilder(
            future: Future.wait([
              _documentsFuture,
              _signersFuture,
            ]),
            builder: (context, AsyncSnapshot<List<dynamic>> snapshot) {
              if (snapshot.connectionState ==
                  ConnectionState.waiting) {
                return const Center(
                    child: CircularProgressIndicator());
              }

              if (snapshot.hasError) {
                return Center(
                  child: Text("Erro: ${snapshot.error}"),
                );
              }

              final documents =
                  snapshot.data![0] as List<Document>;
              final signers =
                  snapshot.data![1] as List<DocumentSigner>;

              /// 🔥 cria lookup O(1)
              final Map<int, DocumentSigner> signerMap = {
                for (var s in signers) s.documentId: s
              };

              final pendingDocs = documents
                  .where((d) {
                    final signer = signerMap[d.documentId];
                    return signer != null && _isPendingForSignature(d);
                  })
                  .toList();

              if (pendingDocs.isEmpty) {
                return const Center(
                  child: Text("Nenhum documento pendente."),
                );
              }

              return ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: pendingDocs.length,
                itemBuilder: (context, index) {
                  final doc = pendingDocs[index];
                  final signer = signerMap[doc.documentId];

                  final bool canSign =
                      signer?.statusId == identityVerified;

                  return Card(
                    elevation: 2,
                    margin:
                        const EdgeInsets.only(bottom: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(12),
                    ),
                    child: InkWell(
                      borderRadius:
                          BorderRadius.circular(12),
                      onTap: () async =>
                          await _openDocument(doc, signer, auth),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          children: [
                            Icon(
                              Icons.description_outlined,
                              color: canSign
                                  ? Theme.of(context)
                                      .primaryColor
                                  : Colors.grey,
                              size: 40,
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    doc.fileName,
                                    style:
                                        GoogleFonts.poppins(
                                      fontWeight:
                                          FontWeight.w600,
                                      fontSize: 16,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    DateFormat(
                                            "dd/MM/yyyy 'às' HH:mm")
                                        .format(
                                            doc.createdAt),
                                    style:
                                        GoogleFonts.poppins(
                                      fontSize: 12,
                                      color: Colors.grey,
                                    ),
                                  ),
                                  if (!canSign)
                                    Padding(
                                      padding:
                                          const EdgeInsets
                                              .only(top: 6),
                                      child: Text(
                                        "Identidade não verificada",
                                        style:
                                            GoogleFonts
                                                .poppins(
                                          color: Colors.red,
                                          fontSize: 11,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                            ),
                            _pendingBadge(),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              );
            },
          );
        },
      ),
    );
  }
}
