import 'dart:convert';
import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../data/repositories/auth_repository.dart';
import '../../../theme/app_colors.dart';

enum CaptureState {
  idle,
  requestingPermission,
  cameraReady,
  capturing,
  processing,
  result,
}

class FacialRecognitionScreen extends StatefulWidget {
  final String userId;
  final int? documentId;
  final bool captureOnly;

  const FacialRecognitionScreen({
    super.key,
    required this.userId,
    this.documentId,
    this.captureOnly = false,
  });

  @override
  State<FacialRecognitionScreen> createState() =>
      _FacialRecognitionScreenState();
}

class _FacialRecognitionScreenState extends State<FacialRecognitionScreen> {
  final AuthRepository _authRepository = AuthRepository();

  CameraController? _controller;
  CaptureState _state = CaptureState.idle;

  String? _message;
  bool? _verificationSuccess;
  int _challengeIndex = 0;
  final Map<String, String> _livenessFrames = {};

  bool _initializing = false;
  bool _capturingFrame = false;

  bool get _isDocumentLiveness => widget.documentId != null;

  final List<Map<String, String>> _challengeSteps = const [
    {
      'key': 'front',
      'title': 'Olhe para frente',
      'subtitle': 'Centralize seu rosto no círculo.',
    },
    {
      'key': 'left',
      'title': 'Vire o rosto para a esquerda',
      'subtitle': 'Mantenha o rosto visível enquanto vira levemente.',
    },
    {
      'key': 'right',
      'title': 'Vire o rosto para a direita',
      'subtitle': 'Agora vire levemente para o outro lado.',
    },
  ];

  Future<void> _startCamera() async {
    if (_initializing) return;

    _initializing = true;

    await _disposeCamera();

    setState(() {
      _state = CaptureState.requestingPermission;
    });

    try {
      final cameras = await availableCameras();

      final front = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );

      final controller = CameraController(
        front,
        ResolutionPreset.high,
        enableAudio: false,
      );

      await controller.initialize();

      if (!mounted) return;

      _controller = controller;

      setState(() {
        _state = CaptureState.cameraReady;
      });
    } on CameraException catch (e) {
      setState(() {
        _verificationSuccess = false;
        _message = "Erro de câmera: ${e.code}";
        _state = CaptureState.result;
      });
    } finally {
      _initializing = false;
    }
  }

  Future<void> _disposeCamera() async {
    final controller = _controller;
    _controller = null;
    if (controller == null) return;
    await _disposeController(controller);
  }

  Future<void> _disposeController(CameraController controller) async {
    try {
      if (controller.value.isInitialized) {
        await controller.pausePreview().catchError((_) {});
      }
      await controller.dispose();
      if (kIsWeb) await Future.delayed(const Duration(milliseconds: 600));
    } catch (e) {
      debugPrint("Erro liberando câmera: $e");
    }
  }


  /// Captura disparada pelo botão: o usuário vira levemente e captura quando
  /// estiver pronto. A câmera permanece ativa entre os passos (não é destruída
  /// e recriada a cada frame), só avançamos o índice do desafio.
  Future<void> _onCapturePressed() async {
    if (_capturingFrame) return;

    final frame = await _captureFrameBase64();
    if (frame == null) return _failCapture();

    if (widget.captureOnly) {
      await _disposeCamera();
      if (!mounted) return;
      Navigator.of(context).pop(frame);
      return;
    }

    if (_isDocumentLiveness) {
      _livenessFrames[_challengeSteps[_challengeIndex]['key']!] = frame;
      if (_challengeIndex < _challengeSteps.length - 1) {
        setState(() => _challengeIndex++);
        return;
      }
      await _submitLiveness();
      return;
    }

    await _submitFace(frame);
  }

  /// Captura um único frame mantendo a câmera viva. Retorna o base64 ou null.
  Future<String?> _captureFrameBase64() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return null;
    try {
      if (mounted) setState(() => _capturingFrame = true);
      final XFile photo = await controller.takePicture();
      final bytes = await photo.readAsBytes();
      return base64Encode(bytes);
    } catch (_) {
      return null;
    } finally {
      if (mounted) setState(() => _capturingFrame = false);
    }
  }

  Future<void> _submitLiveness() async {
    if (!mounted) return;
    setState(() => _state = CaptureState.processing);
    await _disposeCamera();

    final livenessSw = Stopwatch()..start();
    final success = await _authRepository.verifyDocumentLiveness(
      documentId: widget.documentId!,
      frames: _livenessFrames,
    );
    livenessSw.stop();
    debugPrint(
      '[TEMPO] Prova de Vida (round-trip até sucesso=$success) levou '
      '${livenessSw.elapsedMilliseconds} ms',
    );

    if (!mounted) return;
    setState(() {
      _verificationSuccess = success;
      _message = success
          ? "Validação realizada com sucesso!"
          : "Não foi possível validar rosto e movimentação.";
      _state = CaptureState.result;
    });
  }

  Future<void> _submitFace(String base64Image) async {
    if (!mounted) return;
    setState(() => _state = CaptureState.processing);
    await _disposeCamera();

    final faceSw = Stopwatch()..start();
    final success =
        await _authRepository.verifyFace(base64Image, widget.userId);
    faceSw.stop();
    debugPrint(
      '[TEMPO] Reconhecimento Facial (round-trip até sucesso=$success) levou '
      '${faceSw.elapsedMilliseconds} ms',
    );

    if (!mounted) return;
    setState(() {
      _verificationSuccess = success;
      _message = success
          ? "Verificação realizada com sucesso!"
          : "O rosto não corresponde ao cadastro.";
      _state = CaptureState.result;
    });
  }

  Future<void> _failCapture() async {
    await _disposeCamera();
    if (!mounted) return;
    setState(() {
      _verificationSuccess = false;
      _message = "Erro ao capturar imagem.";
      _state = CaptureState.result;
    });
  }

  @override
  void dispose() {
    _disposeCamera();
    super.dispose();
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
      ),
      body: Center(
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          child: _buildUIForState(),
        ),
      ),
    );
  }

  Widget _buildUIForState() {
    switch (_state) {
      case CaptureState.idle:
        return _buildInitialUI();

      case CaptureState.requestingPermission:
      case CaptureState.processing:
      case CaptureState.capturing:
        return const CircularProgressIndicator(
          color: AppColors.primaryButton,
        );

      case CaptureState.cameraReady:
        return _buildCameraUI();

      case CaptureState.result:
        return _buildResultUI();
    }
  }


  Widget _buildInitialUI() {
    final title = _isDocumentLiveness
        ? "Prova de Vida"
        : "Reconhecimento Facial";

    return Container(
      key: const ValueKey('initial'),
      padding: const EdgeInsets.all(32),
      margin: const EdgeInsets.symmetric(horizontal: 24),
      constraints: const BoxConstraints(maxWidth: 500),
      decoration: _buildCardDecoration(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: GoogleFonts.poppins(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: AppColors.primaryText,
            ),
          ),
          const SizedBox(height: 24),
          _buildInstructionRow(
              Icons.lightbulb_outline, "Esteja em um ambiente bem iluminado."),
          _buildInstructionRow(Icons.visibility_off_outlined,
              "Deixe o rosto bem visível. Evite acessórios."),
          _buildInstructionRow(
            Icons.sync_outlined,
            _isDocumentLiveness
                ? "Você capturará frente, esquerda e direita."
                : "Mantenha sua cabeça dentro do círculo.",
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _startCamera,
              style: _buildButtonStyle(),
              child: Text(
                _isDocumentLiveness
                    ? "Iniciar Prova de Vida"
                    : "Iniciar Reconhecimento Facial",
              ),
            ),
          ),
        ],
      ),
    );
  }


  Widget _buildCameraUI() {
    if (_controller == null || !_controller!.value.isInitialized) {
      return const CircularProgressIndicator();
    }

    final step = _isDocumentLiveness
        ? _challengeSteps[_challengeIndex]
        : null;

    return Column(
      key: const ValueKey('camera'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(
          step?['title'] ?? "Mantenha o rosto na câmera",
          style: GoogleFonts.poppins(
            fontSize: 24,
            fontWeight: FontWeight.bold,
            color: AppColors.primaryText,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          step?['subtitle'] ?? "Centralize seu rosto no círculo e capture.",
          style: GoogleFonts.poppins(
            fontSize: 16,
            color: AppColors.primaryText.withValues(alpha: 0.7),
          ),
        ),
        const SizedBox(height: 24),
        Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: 300,
              height: 400,
              child: ClipOval(
                child: AspectRatio(
                  aspectRatio: _controller!.value.aspectRatio,
                  child: CameraPreview(_controller!),
                ),
              ),
            ),
            if (_capturingFrame)
              const CircularProgressIndicator(color: Colors.white),
          ],
        ),
        const SizedBox(height: 16),
        if (_isDocumentLiveness)
          Text(
            "Etapa ${_challengeIndex + 1} de ${_challengeSteps.length}",
            style: GoogleFonts.poppins(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: AppColors.primaryText.withValues(alpha: 0.6),
            ),
          ),
        const SizedBox(height: 16),
        ElevatedButton.icon(
          icon: const Icon(Icons.camera_alt),
          label: Text(
            _isDocumentLiveness
                ? "Capturar ${_challengeIndex + 1}/${_challengeSteps.length}"
                : "Capturar Foto",
          ),
          onPressed: _capturingFrame ? null : _onCapturePressed,
          style: _buildButtonStyle(),
        ),
      ],
    );
  }


  Widget _buildResultUI() {
    final bool isSuccess = _verificationSuccess ?? false;

    return Container(
      key: const ValueKey('result'),
      padding: const EdgeInsets.all(32),
      margin: const EdgeInsets.symmetric(horizontal: 24),
      constraints: const BoxConstraints(maxWidth: 400),
      decoration: _buildCardDecoration(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Image.asset(
            'assets/images/cadeado_ok.png',
            height: 120,
          ),
          const SizedBox(height: 24),
          Text(
            _message ?? "",
            textAlign: TextAlign.center,
            style: GoogleFonts.poppins(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: AppColors.primaryText,
            ),
          ),
          const SizedBox(height: 30),
          ElevatedButton(
            onPressed: () {
              if (isSuccess) {
                Navigator.of(context).pop(true);
              } else {
                setState(() {
                  _state = CaptureState.idle;
                  _verificationSuccess = null;
                  _message = null;
                  _challengeIndex = 0;
                  _capturingFrame = false;
                  _livenessFrames.clear();
                });
              }
            },
            style: _buildButtonStyle(isSuccess: isSuccess),
            child: Text(isSuccess ? "Prosseguir" : "Tentar Novamente"),
          ),
        ],
      ),
    );
  }


  BoxDecoration _buildCardDecoration() => BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 15,
            offset: const Offset(0, 5),
          )
        ],
      );

  ButtonStyle _buildButtonStyle({bool isSuccess = true}) =>
      ElevatedButton.styleFrom(
        backgroundColor:
            isSuccess ? AppColors.primaryButton : Colors.redAccent,
        foregroundColor: Colors.white,
        padding:
            const EdgeInsets.symmetric(horizontal: 40, vertical: 16),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
        textStyle: GoogleFonts.poppins(fontWeight: FontWeight.bold),
      );

  Widget _buildInstructionRow(IconData icon, String text) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          children: [
            Icon(icon, color: AppColors.primaryButton, size: 24),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                text,
                style: GoogleFonts.poppins(
                  fontSize: 15,
                  color: AppColors.primaryText.withValues(alpha: 0.8),
                ),
              ),
            ),
          ],
        ),
      );
}
