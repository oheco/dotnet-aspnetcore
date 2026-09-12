using System.Net;

using var client = new HttpClient(new SocketsHttpHandler { UseProxy = false });
client.Timeout = TimeSpan.FromSeconds(10);
using var response = await client.GetAsync(args[0]);
var content = await response.Content.ReadAsStringAsync();
if (response.StatusCode != HttpStatusCode.OK || !content.Contains(args[1], StringComparison.OrdinalIgnoreCase))
    throw new InvalidOperationException($"Unexpected template response: {response.StatusCode}, {content.Length} characters");
Console.WriteLine($"PASS {new Uri(args[0]).AbsolutePath}: {content.Length} characters");
