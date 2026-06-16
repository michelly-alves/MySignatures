import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../theme/app_colors.dart';

class SessionManager {
  SessionManager._();

  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();

  static bool _handling = false;

  static bool isUnauthorized(int statusCode) {
    if (statusCode == 401) {
      handleUnauthorized();
      return true;
    }
    return false;
  }

  static Future<void> handleUnauthorized() async {
    if (_handling) return;
    _handling = true;

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('jwt_token');
    } catch (_) {}

    final context = navigatorKey.currentContext;
    if (context == null) {
      _handling = false;
      return;
    }

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: Row(
          children: [
            const Icon(Icons.lock_outline, color: Colors.redAccent),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Sessão expirada',
                style: GoogleFonts.poppins(fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        content: Text(
          'Sua sessão expirou ou você não está mais autenticado. '
          'Faça login novamente para continuar.',
          style: GoogleFonts.poppins(fontSize: 14),
        ),
        actions: [
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primaryButton,
              foregroundColor: Colors.white,
            ),
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(
              'Fazer login',
              style: GoogleFonts.poppins(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
    navigatorKey.currentState?.pushNamedAndRemoveUntil('/login', (_) => false);

    _handling = false;
  }
}
