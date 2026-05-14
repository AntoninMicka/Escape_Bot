#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(binding = 1) uniform sampler2D source;

void main()
{
    vec2 uv = qt_TexCoord0;
    vec4 color = texture(source, uv);
    float scanline = sin(uv.y * 900.0) * 0.04;
    float vignette = smoothstep(0.95, 0.25, distance(uv, vec2(0.5)));
    fragColor = vec4((color.rgb - scanline) * vignette, color.a);
}

