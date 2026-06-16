import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../data/models/document_signer_model.dart';
import '../../data/repositories/document_signer_repository.dart';
import '../../theme/app_colors.dart';

class SignersProgress extends StatefulWidget {
  final int documentId;

  const SignersProgress({super.key, required this.documentId});

  @override
  State<SignersProgress> createState() => _SignersProgressState();
}

class _SignersProgressState extends State<SignersProgress> {
  late Future<List<DocumentSigner>> _future;

  @override
  void initState() {
    super.initState();
    _future = DocumentSignerRepository()
        .getDocumentSigners(documentId: widget.documentId);
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
        ],
      ),
    );
  }
}
