import 'package:e_signature_frontend/data/models/document_model.dart';
import 'package:e_signature_frontend/presentation/screens/documents/document_sign_screen.dart';
import 'package:e_signature_frontend/presentation/screens/home_screen.dart';
import 'package:e_signature_frontend/presentation/screens/auth/login_screen.dart';
import 'package:e_signature_frontend/presentation/screens/auth/new_password_screen.dart';
import 'package:e_signature_frontend/presentation/screens/auth/otp_verification_screen.dart';
import 'package:e_signature_frontend/presentation/screens/public/signature_validation_screen.dart';
import 'package:e_signature_frontend/presentation/providers/auth_provider.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'theme/app_colors.dart';
import 'package:provider/provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AuthProvider(),
      child: MaterialApp(
        title: 'E-Signature App',
        theme: ThemeData(
          scaffoldBackgroundColor: AppColors.background,
          primaryColor: AppColors.primaryButton,
          visualDensity: VisualDensity.adaptivePlatformDensity,
          textTheme: GoogleFonts.poppinsTextTheme(),
        ),
        home: _getInitialScreen(),
        onGenerateRoute: _onGenerateRoute,
        debugShowCheckedModeBanner: false,
      ),
    );
  }

  Widget _getInitialScreen() {
    final uri = Uri.base;

    if (uri.path.contains('/set-password')) {
      final token = uri.queryParameters['token'] ?? '';
      return SetPasswordScreen(token: token);
    }

    if (uri.path.contains('/validate')) {
      return SignatureValidationScreen(
        initialCode: uri.queryParameters['code'],
      );
    }

    return Consumer<AuthProvider>(
      builder: (context, auth, _) {
        if (auth.isAuthenticated) {
          if (auth.requiresOtpVerification) {
            return OtpVerificationScreen(
              email: auth.userEmail ?? '',
              sendOnOpen: true,
              goHomeAfterVerification: true,
            );
          }
          return const HomeScreen();
        } else {
          return const LoginScreen();
        }
      },
    );
  }

  Route<dynamic> _onGenerateRoute(RouteSettings settings) {
    final uri = Uri.parse(settings.name ?? '');

    if (uri.path == '/set-password') {
      final token = uri.queryParameters['token'] ?? '';
      return MaterialPageRoute(
        builder: (_) => SetPasswordScreen(token: token),
      );
    }

    if (uri.path == '/validate') {
      return MaterialPageRoute(
        builder: (_) => SignatureValidationScreen(
          initialCode: uri.queryParameters['code'],
        ),
      );
    }

    switch (settings.name) {
      case '/login':
        return MaterialPageRoute(builder: (_) => const LoginScreen());
      case '/home':
        return MaterialPageRoute(builder: (_) => const HomeScreen());
      case '/validate':
        return MaterialPageRoute(
          builder: (_) => const SignatureValidationScreen(),
        );
      case '/document-sign':
        final document = settings.arguments;
        if (document is Document) {
          return MaterialPageRoute(
            builder: (_) => DocumentSignScreen(document: document),
          );
        }
        return MaterialPageRoute(builder: (_) => const HomeScreen());
      default:
        return MaterialPageRoute(builder: (_) => const LoginScreen());
    }
  }
}
