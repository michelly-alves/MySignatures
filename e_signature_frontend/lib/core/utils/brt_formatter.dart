import 'package:intl/intl.dart';

String formatBrt(
  DateTime dt, {
  String pattern = "dd/MM/yyyy 'às' HH:mm",
}) {
  final utc = dt.isUtc
      ? dt
      : DateTime.utc(
          dt.year,
          dt.month,
          dt.day,
          dt.hour,
          dt.minute,
          dt.second,
          dt.millisecond,
        );
  final brt = utc.subtract(const Duration(hours: 3));
  return '${DateFormat(pattern).format(brt)} (BRT)';
}
