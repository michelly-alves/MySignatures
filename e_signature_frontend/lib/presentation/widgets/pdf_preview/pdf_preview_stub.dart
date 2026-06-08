import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class PdfPreview extends StatelessWidget {
  final Uint8List bytes;
  final String fileName;
  final ValueNotifier<bool>? pointerEventsNotifier;

  const PdfPreview({
    super.key,
    required this.bytes,
    required this.fileName,
    this.pointerEventsNotifier,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Visualização de PDF disponível na versão Web.',
          textAlign: TextAlign.center,
          style: GoogleFonts.poppins(fontSize: 16),
        ),
      ),
    );
  }
}
