<?php
$baseDir = __DIR__ . '/plists';

function resolve_plist($baseDir, $model, $build) {
    if (!$model || !$build || strpos($model, '..') !== false || strpos($build, '..') !== false) {
        return null;
    }
    $filePath = $baseDir . '/' . $model . '/' . $build . '/patched.plist';
    return file_exists($filePath) ? $filePath : null;
}

if (isset($_GET['support_query'])) {
    $filePath = resolve_plist($baseDir, $_GET['model'] ?? '', $_GET['build'] ?? '');
    header('Content-Type: application/json');
    echo json_encode(['supported' => $filePath !== null]);
    exit();
}

$userAgent = $_SERVER['HTTP_USER_AGENT'] ?? '';

$model = null;
$build = null;

if (preg_match('/model\/([a-zA-Z0-9,]+)/', $userAgent, $mMatches)) {
    $model = $mMatches[1];
}

if (preg_match('/build\/([a-zA-Z0-9]+)/', $userAgent, $bMatches)) {
    $build = $bMatches[1];
}

$filePath = resolve_plist($baseDir, $model, $build);

if ($filePath !== null) {
    header('Content-Description: File Transfer');
    header('Content-Encoding: identity');
    header('Content-Type: application/xml');
    header('Content-Disposition: attachment; filename="patched.plist"');
    header('Content-Length: ' . filesize($filePath));
    header('Cache-Control: must-revalidate');
    header('Pragma: public');
    
    readfile($filePath);
    exit();
}

http_response_code(403);
echo "Forbidden";
exit();
?>