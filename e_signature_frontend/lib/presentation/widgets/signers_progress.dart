import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../data/models/document_signer_model.dart';
import '../../data/repositories/document_signer_repository.dart';
import '../../theme/app_colors.dart';

class SignersProgress extends StatefulWidget {
  final int documentId;

  final bool canManage;

  const SignersProgress({
    super.key,
    required this.documentId,
    this.canManage = false,
  });

  @override
  State<SignersProgress> createState() => _SignersProgressState();
}

class _SignersProgressState extends State<SignersProgress> {
  final DocumentSignerRepository _repo = DocumentSignerRepository();
  late Future<List<DocumentSigner>> _future;
  int? _uploadingSignerId;

  @override
  void initState() {
    super.initState();
    _future = _repo.getDocumentSigners(documentId: widget.documentId);
  }

  void _reload() {
    setState(() {
      _future = _repo.getDocumentSigners(documentId: widget.documentId);
    });
  }

  bool _canReplacePhoto(int statusId) =>
      widget.canManage && statusId != 2 && statusId != 4;

  Future<void> _replacePhoto(DocumentSigner signer) async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.image,
      withData: true,
    );
    if (picked == null || picked.files.isEmpty) return;
    final file = picked.files.first;
    if (file.bytes == null) return;

    setState(() => _uploadingSignerId = signer.signerId);
    final error = await _repo.replaceSignerPhoto(
      documentId: widget.documentId,
      signerId: signer.signerId,
      fileName: file.name,
      bytes: file.bytes!,
    );
    if (!mounted) return;
    setState(() => _uploadingSignerId = null);

    final messenger = ScaffoldMessenger.of(context);
    if (error == null) {
      messenger.showSnackBar(const SnackBar(
        backgroundColor: Colors.green,
        content: Text('Foto atualizada. O signatário pode validar novamente.'),
      ));
      _reload();
    } else {
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          icon: const Icon(Icons.image_not_supported_outlined,
              color: Colors.redAccent, size: 40),
          title: Text('Problema com a foto',
              style: GoogleFonts.poppins(fontWeight: FontWeight.bold)),
          content: Text(error, style: GoogleFonts.poppins(fontSize: 14)),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Entendi'),
            ),
          ],
        ),
      );
    }
  }

  ({IconData icon, Color color, String label}) _statusVisual(int statusId) {
    switch (statusId) {
      case 4: 
        return (icon: Icons.check_circle, color: Colors.green.shade600, label: 'Assinou');
      case 2: 
        return (
          icon: Icons.how_to_reg_outlined,
          color: Colors.blue.shade600,
          label: 'Identidade verificada — falta assinar'
        );
      case 3: 
        return (icon: Icons.error_outline, color: Colors.red.shade600, label: 'Falha na verificação');
      default: 
        return (
          icon: Icons.hourglass_empty,
          color: Colors.orange.shade700,
          label: 'Aguardando assinatura'
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<DocumentSigner>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              'Carregando signatários...',
              style: GoogleFonts.poppins(color: Colors.grey.shade600, fontSize: 12),
            ),
          );
        }

        final signers = snapshot.data ?? const <DocumentSigner>[];
        if (signers.isEmpty) return const SizedBox.shrink();

        final signedCount = signers.where((s) => s.hasSigned).length;
        final total = signers.length;
        final allSigned = signedCount == total;

        return Container(
          margin: const EdgeInsets.only(top: 10),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppColors.textFieldFill,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: AppColors.textFieldBorder),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    allSigned ? Icons.verified_outlined : Icons.groups_outlined,
                    size: 18,
                    color: allSigned ? Colors.green.shade700 : AppColors.primaryButton,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '$signedCount de $total assinaram',
                    style: GoogleFonts.poppins(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primaryText,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: total == 0 ? 0 : signedCount / total,
                  minHeight: 6,
                  backgroundColor: Colors.grey.shade300,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    allSigned ? Colors.green.shade600 : AppColors.primaryButton,
                  ),
                ),
              ),
              const SizedBox(height: 10),
              ...signers.map(_buildSignerRow),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSignerRow(DocumentSigner signer) {
    final visual = _statusVisual(signer.statusId);
    final name = (signer.signerName != null && signer.signerName!.isNotEmpty)
        ? signer.signerName!
        : 'Signatário #${signer.signerId}';

    final isUploading = _uploadingSignerId == signer.signerId;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(visual.icon, size: 16, color: visual.color),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: GoogleFonts.poppins(
                    fontSize: 13,
                    color: AppColors.primaryText,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  visual.label,
                  style: GoogleFonts.poppins(fontSize: 11, color: visual.color),
                ),
              ],
            ),
          ),
          if (isUploading)
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else if (_canReplacePhoto(signer.statusId))
            TextButton.icon(
              onPressed: _uploadingSignerId != null
                  ? null
                  : () => _replacePhoto(signer),
              icon: const Icon(Icons.photo_camera_outlined, size: 16),
              label: const Text('Trocar foto'),
              style: TextButton.styleFrom(
                foregroundColor: AppColors.primaryButton,
                padding: const EdgeInsets.symmetric(horizontal: 8),
                visualDensity: VisualDensity.compact,
                textStyle: GoogleFonts.poppins(fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}
