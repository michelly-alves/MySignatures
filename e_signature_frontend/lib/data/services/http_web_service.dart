import 'dart:convert';
import 'dart:html' as html;

class HttpWebService {
  final String baseUrl;

  HttpWebService(this.baseUrl);

  Future<html.HttpRequest> post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final request = html.HttpRequest();

    request
      ..open("POST", "$baseUrl$path")
      ..setRequestHeader("Content-Type", "application/json")
      ..withCredentials = true;

    request.send(jsonEncode(body));

    await request.onLoad.first;
    return request;
  }

  Future<html.HttpRequest> get(String path) async {
    final request = html.HttpRequest();

    request
      ..open("GET", "$baseUrl$path")
      ..withCredentials = true;

    request.send();

    await request.onLoad.first;
    return request;
  }
}
