use glam::{Mat4, Vec3, Vec4};
use serde::{Deserialize, Serialize};

#[derive(Clone, Deserialize, Serialize)]
pub struct Manifest {
    pub version: u32,
    pub dataset_id: String,
    pub field: String,
    pub dimensions: [usize; 3],
    pub origin: [f64; 3],
    pub spacing: [f64; 3],
    pub render_origin: [f64; 3],
    pub value_range: [f64; 2],
    pub units: String,
    pub components: usize,
    pub timestep: usize,
    pub mode: String,
}

#[derive(Clone, Default, Deserialize, Serialize)]
pub struct Mesh {
    pub positions: Vec<[f64; 3]>,
    pub indices: Vec<u32>,
    pub values: Vec<f64>,
}

#[derive(Clone, Deserialize, Serialize)]
pub struct Scene {
    pub manifest: Manifest,
    pub mesh: Mesh,
}

impl Scene {
    pub fn validate(&self) -> Result<(), String> {
        let m = &self.mesh;
        if self.manifest.version != 1 || m.positions.len() != m.values.len()
            || m.indices.len() % 3 != 0 || m.positions.len() > 80000
            || m.indices.iter().any(|&i| i as usize >= m.positions.len())
            || m.positions.iter().flatten().chain(m.values.iter()).any(|v| !v.is_finite())
            || self.manifest.spacing.iter().any(|s| !s.is_finite() || *s <= 0.0)
            || self.manifest.dimensions.contains(&0)
        {
            return Err("Invalid or unsupported scientific scene".into());
        }
        Ok(())
    }

    pub fn bounds(&self) -> (Vec3, f32) {
        let extent = Vec3::from_array(std::array::from_fn(|i|
            ((self.manifest.dimensions[i] - 1) as f64 * self.manifest.spacing[i]) as f32));
        (extent * 0.5, extent.length().max(0.01))
    }

    pub fn matrix(&self, yaw: f32, pitch: f32, zoom: f32, aspect: f32) -> Mat4 {
        let (center, radius) = self.bounds();
        let direction = Vec3::new(yaw.cos()*pitch.cos(), pitch.sin(), yaw.sin()*pitch.cos());
        Mat4::perspective_rh(0.75, aspect.max(0.01), radius*0.001, radius*100.0)
            * Mat4::look_at_rh(center + direction*radius*zoom, center, Vec3::Y)
    }

    /// Return a physical coordinate on the closest visible triangle.
    pub fn pick(&self, matrix: Mat4, ndc: [f32; 2]) -> Option<[f64; 3]> {
        let inverse = matrix.inverse();
        let near = inverse * Vec4::new(ndc[0], ndc[1], 0.0, 1.0);
        let far = inverse * Vec4::new(ndc[0], ndc[1], 1.0, 1.0);
        let origin = near.truncate()/near.w;
        let direction = (far.truncate()/far.w-origin).normalize();
        let mut closest = f32::INFINITY;
        for tri in self.mesh.indices.chunks_exact(3) {
            let [a,b,c] = std::array::from_fn::<_,3,_>(|i| Vec3::from_array(self.mesh.positions[tri[i] as usize].map(|v| v as f32)));
            let e1 = b-a;
            let e2 = c-a;
            let h = direction.cross(e2);
            let det = e1.dot(h);
            if det.abs() < 1e-10 { continue; }
            let s = origin-a;
            let u = s.dot(h)/det;
            let q = s.cross(e1);
            let v = direction.dot(q)/det;
            let distance = e2.dot(q)/det;
            if u >= 0.0 && v >= 0.0 && u+v <= 1.0 && distance >= 0.0 { closest = closest.min(distance); }
        }
        closest.is_finite().then(|| {
            let hit = (origin+closest*direction).to_array();
            std::array::from_fn(|i| self.manifest.render_origin[i] + hit[i] as f64)
        })
    }

    pub fn demo() -> Self {
        let mut mesh = Mesh::default();
        let n = 32;
        for y in 0..n { for x in 0..n {
            let a = x as f64/(n-1) as f64*2.0-1.0;
            let b = y as f64/(n-1) as f64*2.0-1.0;
            let z = (a*3.0).sin()*(b*3.0).cos()*0.3;
            mesh.positions.push([a+1.0,b+1.0,z+0.3]);
            mesh.values.push(z);
            if x+1<n && y+1<n { let i=(y*n+x) as u32; mesh.indices.extend([i,i+1,i+n as u32,i+1,i+n as u32+1,i+n as u32]); }
        }}
        Self {manifest: Manifest {version:1,dataset_id:"local-demo".into(),field:"演示曲面（非计算结果）".into(),
            dimensions:[32,32,2],origin:[0.0;3],spacing:[2.0/31.0,2.0/31.0,0.6],render_origin:[0.0;3],
            value_range:[-0.3,0.3],units:"演示".into(),components:1,timestep:0,mode:"demo".into()},mesh}
    }
}

pub fn color(value: f64, range: [f64;2]) -> [f32;3] {
    let t = if range[1] > range[0] {((value-range[0])/(range[1]-range[0])).clamp(0.0,1.0) as f32} else {0.5};
    // Sequential blue/cyan/yellow, shared with the web client.
    if t < 0.5 { [0.12+0.08*t*2.0,0.22+0.5*t*2.0,0.55+0.1*t*2.0] }
    else { let u=(t-0.5)*2.0; [0.2+0.75*u,0.72+0.1*u,0.65-0.45*u] }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn validates_indices_and_scientific_metadata() {
        let mut s=Scene::demo(); assert!(s.validate().is_ok());
        s.mesh.indices[0]=u32::MAX; assert!(s.validate().is_err());
    }
    #[test] fn picking_returns_physical_coordinates() {
        let mut s=Scene::demo();
        s.mesh=Mesh {positions:vec![[-1.,-1.,0.5],[1.,-1.,0.5],[0.,1.,0.5]],indices:vec![0,1,2],values:vec![0.;3]};
        s.manifest.render_origin=[1e9,2.,3.];
        let p=s.pick(Mat4::IDENTITY,[0.,0.]).unwrap();
        assert_eq!(p,[1e9,2.,3.5]); assert!(s.pick(Mat4::IDENTITY,[3.,3.]).is_none());
    }
}
