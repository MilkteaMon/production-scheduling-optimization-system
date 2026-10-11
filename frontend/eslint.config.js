import tseslint from 'typescript-eslint';
export default tseslint.config({ignores:['dist/**','src/api/schema.d.ts']},...tseslint.configs.recommended,{rules:{'@typescript-eslint/no-explicit-any':'off'}});
