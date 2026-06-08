import 'dart:html' as html;
import 'dart:typed_data';
import 'dart:ui_web' as ui;

import 'package:flutter/material.dart';

class PdfPreview extends StatefulWidget {
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
  State<PdfPreview> createState() => _PdfPreviewState();
}

class _PdfPreviewState extends State<PdfPreview> {
  late final String _viewType;
  String? _objectUrl;
  html.IFrameElement? _iframe;

  void _applyPointerEvents() {
    final enabled = widget.pointerEventsNotifier?.value ?? true;
    _iframe?.style.pointerEvents = enabled ? 'auto' : 'none';
  }

  @override
  void initState() {
    super.initState();

    _viewType = 'pdf-preview-${DateTime.now().microsecondsSinceEpoch}';
    final blob = html.Blob([widget.bytes], 'application/pdf');
    _objectUrl = html.Url.createObjectUrlFromBlob(blob);

    ui.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
      _iframe = html.IFrameElement()
        ..src = _objectUrl!
        ..title = widget.fileName
        ..style.border = '0'
        ..style.width = '100%'
        ..style.height = '100%'
        ..allowFullscreen = true;
      _applyPointerEvents();
      return _iframe!;
    });

    widget.pointerEventsNotifier?.addListener(_applyPointerEvents);
  }

  @override
  void dispose() {
    widget.pointerEventsNotifier?.removeListener(_applyPointerEvents);
    final objectUrl = _objectUrl;
    if (objectUrl != null) {
      html.Url.revokeObjectUrl(objectUrl);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return HtmlElementView(viewType: _viewType);
  }
}
