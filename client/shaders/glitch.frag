#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float intensity;
};

layout(binding = 1) uniform sampler2D source;

void main()
{
    vec2 uv = qt_TexCoord0;
    float offset = sin(uv.y * 80.0) * 0.008 * intensity;
    float r = texture(source, uv + vec2(offset, 0.0)).r;
    float g = texture(source, uv).g;
    float b = texture(source, uv - vec2(offset, 0.0)).b;
    fragColor = vec4(r, g, b, 1.0) * qt_Opacity;
}

